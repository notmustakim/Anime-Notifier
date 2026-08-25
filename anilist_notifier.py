"""
AniList Episode Notifier
-------------------------
Watches your AniList "Currently Watching" list and emails you when new
episodes are about to air or have just been released.

Improvements over the original version:
  - Real logging (console + rotating file) instead of print()
  - Robust HTTP session with retries/backoff and timeouts (handles
    AniList's rate limiting and transient network errors)
  - GraphQL error responses are detected and reported instead of
    silently returning an empty list
  - HTML-escapes all user-supplied text (titles, descriptions) before
    building the email, preventing broken/garbled emails from special
    characters
  - Secrets (SMTP password) can come from an environment variable so
    they don't have to live in plaintext config.json
  - Config is validated on startup with clear error messages
  - State file no longer grows forever - stale entries are pruned
  - Configurable poll interval (was hardcoded to 1 hour)
  - --once flag to run a single check (handy for running via cron /
    systemd timer instead of an infinite loop)
  - Graceful Ctrl+C / SIGTERM shutdown
  - Type hints + dataclass for anime entries for clarity
"""

import argparse
import html
import json
import logging
import os
import re
import signal
import smtplib
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ANILIST_API_URL = "https://graphql.anilist.co"

WATCHING_QUERY = """
query ($username: String) {
    MediaListCollection(userName: $username, type: ANIME, status: CURRENT) {
        lists {
            entries {
                media {
                    id
                    title { romaji english }
                    nextAiringEpisode {
                        episode
                        timeUntilAiring
                        airingAt
                    }
                    siteUrl
                    coverImage { large }
                    description
                    averageScore
                    genres
                    episodes
                    status
                }
                progress
            }
        }
    }
}
"""


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #

@dataclass
class AnimeEntry:
    id: int
    title: str
    progress: int
    next_episode: int | None
    seconds_until: int | None
    airing_at: int | None
    url: str
    cover: str
    description: str
    score: Any
    genres: list[str] = field(default_factory=list)
    total_episodes: Any = "?"
    status: str = ""


class ConfigError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Notifier
# --------------------------------------------------------------------------- #

class AniListNotifier:
    STATE_MAX_AGE_ENTRIES = 500

    def __init__(
        self,
        config_file: str = "config.json",
        state_file: str = "anilist_state.json"
    ):
        self.state_file = Path(state_file)
        self.logger = self._setup_logging()
        self.config = self._load_config(config_file)
        self._apply_config()
        self.state = self._load_state()
        self.session = self._build_session()
        self._stop = False

        signal.signal(signal.SIGINT, self._handle_stop)
        signal.signal(signal.SIGTERM, self._handle_stop)

    # ---- setup ------------------------------------------------------------- #

    def _setup_logging(self) -> logging.Logger:
        logger = logging.getLogger("anilist_notifier")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            "%Y-%m-%d %H:%M:%S"
        )

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        logger.addHandler(console)

        file_handler = RotatingFileHandler(
            "anilist_notifier.log",
            maxBytes=1_000_000,
            backupCount=3
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

        return logger

    def _load_config(self, config_file: str) -> dict:
        path = Path(config_file)

        if not path.exists():
            raise ConfigError(
                f"Config file not found: {config_file}"
            )

        try:
            with open(path, "r") as f:
                config = json.load(f)

        except json.JSONDecodeError as e:
            raise ConfigError(
                f"Config file is not valid JSON: {e}"
            ) from e

        required = {
            "email": [
                "sender",
                "receiver",
                "smtp_server",
                "smtp_port"
            ],
            "anilist": [
                "username"
            ],
        }

        for section, keys in required.items():
            if section not in config:
                raise ConfigError(
                    f"Missing required config section: '{section}'"
                )

            for key in keys:
                if key not in config[section]:
                    raise ConfigError(
                        f"Missing required config key: "
                        f"'{section}.{key}'"
                    )

        return config

    def _apply_config(self) -> None:
        email_cfg = self.config["email"]

        self.email_sender = email_cfg["sender"]

        # Prefer environment variable for password.
        self.email_password = os.environ.get(
            "ANILIST_NOTIFIER_SMTP_PASSWORD",
            email_cfg.get("password")
        )

        if not self.email_password:
            raise ConfigError(
                "No SMTP password found. Set it in config.json under "
                "email.password, or export "
                "ANILIST_NOTIFIER_SMTP_PASSWORD."
            )

        self.email_receiver = email_cfg["receiver"]
        self.smtp_server = email_cfg["smtp_server"]
        self.smtp_port = email_cfg["smtp_port"]

        self.sender_name = email_cfg.get(
            "sender_name",
            "Anime Notifier"
        )

        self.anilist_user = self.config["anilist"]["username"]

        self.hours_before_notify = self.config.get(
            "hours_before_notify",
            24
        )

        self.poll_interval_seconds = self.config.get(
            "poll_interval_seconds",
            3600
        )

    def _build_session(self) -> requests.Session:
        session = requests.Session()

        retries = Retry(
            total=4,
            backoff_factor=1.5,
            status_forcelist=[
                429,
                500,
                502,
                503,
                504
            ],
            allowed_methods=["POST"],
            respect_retry_after_header=True,
        )

        adapter = HTTPAdapter(max_retries=retries)

        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def _handle_stop(self, signum, frame) -> None:
        self.logger.info(
            "Received stop signal, shutting down after this cycle..."
        )

        self._stop = True

    # ---- state ------------------------------------------------------------- #

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)

            except (json.JSONDecodeError, OSError) as e:
                self.logger.warning(
                    f"Could not read state file ({e}); "
                    "starting fresh."
                )

        return {
            "notified_upcoming": [],
            "notified_released": []
        }

    def _save_state(self) -> None:
        # Prevent unbounded growth.
        for key in (
            "notified_upcoming",
            "notified_released"
        ):
            entries = self.state.get(key, [])

            if len(entries) > self.STATE_MAX_AGE_ENTRIES:
                self.state[key] = entries[
                    -self.STATE_MAX_AGE_ENTRIES:
                ]

        tmp_path = self.state_file.with_suffix(".tmp")

        with open(tmp_path, "w") as f:
            json.dump(
                self.state,
                f,
                indent=2
            )

        tmp_path.replace(self.state_file)

    # ---- AniList API ------------------------------------------------------- #

    def get_watching_list(self) -> list[AnimeEntry]:
        try:
            response = self.session.post(
                ANILIST_API_URL,
                json={
                    "query": WATCHING_QUERY,
                    "variables": {
                        "username": self.anilist_user
                    }
                },
                timeout=30,
            )

            response.raise_for_status()
            data = response.json()

        except requests.exceptions.RequestException as e:
            self.logger.error(
                f"Network error contacting AniList: {e}"
            )
            return []

        except ValueError as e:
            self.logger.error(
                f"AniList returned invalid JSON: {e}"
            )
            return []

        if "errors" in data:
            messages = "; ".join(
                err.get("message", "unknown error")
                for err in data["errors"]
            )

            self.logger.error(
                f"AniList GraphQL error: {messages}"
            )

            return []

        watching: list[AnimeEntry] = []

        lists = (
            data
            .get("data", {})
            .get("MediaListCollection", {})
            .get("lists", [])
            or []
        )

        for media_list in lists:
            for entry in media_list.get("entries", []):

                media = entry["media"]

                next_airing = media.get(
                    "nextAiringEpisode"
                )

                if not next_airing:
                    continue

                description = (
                    media.get("description", "")
                    or ""
                )

                if description:
                    description = re.sub(
                        "<[^<]+?>",
                        "",
                        description
                    )

                    description = (
                        description[:150] + "..."
                        if len(description) > 150
                        else description
                    )

                watching.append(
                    AnimeEntry(
                        id=media["id"],
                        title=(
                            media["title"]["romaji"]
                            or media["title"]["english"]
                            or "Unknown"
                        ),
                        progress=entry.get(
                            "progress",
                            0
                        ),
                        next_episode=next_airing.get(
                            "episode"
                        ),
                        seconds_until=next_airing.get(
                            "timeUntilAiring"
                        ),
                        airing_at=next_airing.get(
                            "airingAt"
                        ),
                        url=media.get(
                            "siteUrl",
                            ""
                        ),
                        cover=media.get(
                            "coverImage",
                            {}
                        ).get(
                            "large",
                            ""
                        ),
                        description=description,
                        score=media.get(
                            "averageScore",
                            "N/A"
                        ),
                        genres=(
                            media.get("genres")
                            or []
                        )[:3],
                        total_episodes=media.get(
                            "episodes",
                            "?"
                        ),
                        status=media.get(
                            "status",
                            ""
                        ),
                    )
                )

        return watching

    # ---- formatting -------------------------------------------------------- #

    @staticmethod
    def format_time(seconds: int) -> str:
        if seconds <= 0:
            return "Released Now!"

        days = seconds // 86400
        hours = (
            seconds % 86400
        ) // 3600

        minutes = (
            seconds % 3600
        ) // 60

        parts = []

        if days > 0:
            parts.append(
                f"{days}d"
            )

        if hours > 0:
            parts.append(
                f"{hours}h"
            )

        if minutes > 0 and days == 0:
            parts.append(
                f"{minutes}m"
            )

        return (
            " ".join(parts)
            if parts
            else "soon"
        )

    def create_email_html(
        self,
        episodes: list[dict],
        notification_type: str = "upcoming"
    ) -> str:

        """Create a clean, properly formatted email body."""

        if notification_type == "release":

            header_emoji = "🎉"
            header_title = "New Episodes Released"
            header_sub = "Ready to watch right now"

            accent = "#10b981"
            accent_dark = "#047857"
            accent_soft = "#ecfdf5"
            accent_text = "#047857"

            pill_label = "Available now"
            cta_label = "Watch now"

        else:

            header_emoji = "⏰"
            header_title = "Upcoming Episodes"
            header_sub = "Airing soon on your watch list"

            accent = "#f59e0b"
            accent_dark = "#b45309"
            accent_soft = "#fffbeb"
            accent_text = "#b45309"

            pill_label = None
            cta_label = "View on AniList"

        episode_cards = ""

        for ep in episodes:

            title = html.escape(
                str(ep["title"])
            )

            description = html.escape(
                str(ep.get("description", ""))
            )

            url = html.escape(
                str(ep.get("url", "")),
                quote=True
            )

            cover_img_url = html.escape(
                str(ep.get("cover", "")),
                quote=True
            )

            time_display = html.escape(
                pill_label
                or str(ep["time_until"])
            )

            if cover_img_url:

                cover_html = (
                    f'<img src="{cover_img_url}" alt="" width="72" '
                    f'style="width: 72px; height: 104px; '
                    f'object-fit: cover; border-radius: 8px; '
                    f'display: block; border: 1px solid #e5e7eb;">'
                )

            else:

                cover_html = (
                    f'<div style="width: 72px; height: 104px; '
                    f'background: {accent_soft}; border-radius: 8px; '
                    f'display: flex; align-items: center; '
                    f'justify-content: center; '
                    f'color: {accent_dark}; font-size: 26px; '
                    f'border: 1px solid #e5e7eb;">🎬</div>'
                )

            genres_html = "".join(
                f'<span style="background: #f3f4f6; '
                f'padding: 3px 9px; border-radius: 999px; '
                f'font-size: 11px; margin: 0 4px 4px 0; '
                f'color: #4b5563; display: inline-block;">'
                f'{html.escape(g)}</span>'
                for g in ep.get(
                    "genres",
                    []
                )[:3]
            )

            score_html = ""

            if (
                ep.get("score")
                and ep["score"] != "N/A"
            ):
                score_html = (
                    f'<span style="background: #f3f4f6; '
                    f'padding: 3px 9px; border-radius: 999px; '
                    f'font-size: 11px; margin: 0 4px 4px 0; '
                    f'color: #4b5563; display: inline-block;">'
                    f'⭐ {html.escape(str(ep["score"]))}%</span>'
                )

            eps_html = ""

            if (
                ep.get("total_episodes")
                and ep["total_episodes"] != "?"
            ):
                eps_html = (
                    f'<span style="background: #f3f4f6; '
                    f'padding: 3px 9px; border-radius: 999px; '
                    f'font-size: 11px; margin: 0 4px 4px 0; '
                    f'color: #4b5563; display: inline-block;">'
                    f'📺 {html.escape(str(ep["total_episodes"]))} '
                    f'total</span>'
                )

            meta_row = "".join(
                [
                    genres_html,
                    score_html,
                    eps_html
                ]
            )

            description_html = (
                f'<div style="font-size: 13px; '
                f'color: #6b7280; margin: 8px 0 0 0; '
                f'line-height: 1.5;">'
                f'{description}</div>'
                if description
                else ""
            )

            episode_cards += f"""
            <table cellpadding="0" cellspacing="0" border="0"
                   width="100%"
                   style="background: #ffffff;
                          border-radius: 12px;
                          margin-bottom: 14px;
                          border: 1px solid #e5e7eb;">
                <tr>
                    <td style="padding: 18px;">
                        <table cellpadding="0" cellspacing="0"
                               border="0" width="100%">
                            <tr>
                                <td style="width: 72px;
                                           vertical-align: top;
                                           padding-right: 16px;">
                                    {cover_html}
                                </td>

                                <td style="vertical-align: top;">

                                    <div style="font-size: 16px;
                                                font-weight: 700;
                                                color: #111827;
                                                line-height: 1.3;
                                                margin-bottom: 6px;">
                                        {title}
                                    </div>

                                    <table cellpadding="0"
                                           cellspacing="0"
                                           border="0">
                                        <tr>

                                            <td style="background: {accent};
                                                       color: #ffffff;
                                                       font-size: 12px;
                                                       font-weight: 700;
                                                       padding: 3px 10px;
                                                       border-radius: 6px;">
                                                EP {ep['next_episode']}
                                  
