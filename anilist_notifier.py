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
  - Configurable timezone support
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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

        # Load timezone from config (default to UTC)
        self.timezone = self.config.get("timezone", "UTC")

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
                                            </td>

                                            <td style="width: 8px;"></td>

                                            <td style="background: {accent_soft};
                                                       color: {accent_text};
                                                       font-size: 12px;
                                                       font-weight: 600;
                                                       padding: 3px 10px;
                                                       border-radius: 6px;">
                                                ⏱ {time_display}
                                            </td>

                                        </tr>
                                    </table>

                                    <div style="font-size: 12px;
                                                color: #9ca3af;
                                                margin-top: 8px;">
                                        You're caught up through
                                        Episode {ep['progress']}
                                    </div>

                                    {description_html}

                                    <div style="margin-top: 10px;">
                                        {meta_row}
                                    </div>

                                    <div style="margin-top: 12px;">

                                        <a href="{url}"
                                           style="display: inline-block;
                                                  background: {accent_dark};
                                                  color: #ffffff;
                                                  padding: 8px 16px;
                                                  border-radius: 8px;
                                                  text-decoration: none;
                                                  font-weight: 600;
                                                  font-size: 13px;">
                                            {cta_label} →
                                        </a>

                                    </div>

                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
            """

        anilist_user_escaped = html.escape(
            self.anilist_user
        )

        plural = (
            ""
            if len(episodes) == 1
            else "s"
        )

        # Get timezone from config
        try:
            tz = ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError:
            self.logger.warning(f"Timezone '{self.timezone}' not found, falling back to UTC")
            tz = ZoneInfo("UTC")

        checked_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
        timezone_escaped = html.escape(self.timezone)

        return f"""
        <!DOCTYPE html>
        <html>

        <head>
            <meta charset="UTF-8">
            <meta name="viewport"
                  content="width=device-width, initial-scale=1.0">
            <meta name="color-scheme"
                  content="light">
        </head>

        <body style="font-family: -apple-system,
                      BlinkMacSystemFont, 'Segoe UI',
                      Roboto, Arial, sans-serif;
                      background: #f4f4f5;
                      padding: 24px 16px;
                      margin: 0;">

            <table cellpadding="0"
                   cellspacing="0"
                   border="0"
                   align="center"
                   width="100%"
                   style="max-width: 600px;
                          margin: 0 auto;">

                <tr>
                    <td>

                        <!-- Header -->

                        <table cellpadding="0"
                               cellspacing="0"
                               border="0"
                               width="100%"
                               style="background: {accent};
                                      border-radius: 14px;
                                      padding: 26px 24px;
                                      margin-bottom: 20px;">

                            <tr>
                                <td style="color: #ffffff;">

                                    <table cellpadding="0"
                                           cellspacing="0"
                                           border="0"
                                           width="100%">

                                        <tr>

                                            <td style="vertical-align: middle;">

                                                <div style="font-size: 13px;
                                                            opacity: 0.85;
                                                            font-weight: 600;
                                                            letter-spacing: 0.03em;
                                                            text-transform: uppercase;">
                                                    Anime Notifier ·
                                                    {anilist_user_escaped}
                                                </div>

                                                <div style="font-size: 24px;
                                                            font-weight: 700;
                                                            margin-top: 4px;">
                                                    {header_emoji}
                                                    {header_title}
                                                </div>

                                                <div style="font-size: 14px;
                                                            opacity: 0.9;
                                                            margin-top: 3px;">
                                                    {header_sub}
                                                </div>

                                            </td>

                                            <td align="right"
                                                style="vertical-align: middle;">

                                                <div style="background: rgba(255,255,255,0.2);
                                                            color: #ffffff;
                                                            font-size: 20px;
                                                            font-weight: 700;
                                                            padding: 8px 16px;
                                                            border-radius: 10px;
                                                            text-align: center;">

                                                    {len(episodes)}

                                                    <div style="font-size: 10px;
                                                                font-weight: 600;
                                                                opacity: 0.9;
                                                                text-transform: uppercase;">
                                                        ep{plural}
                                                    </div>

                                                </div>

                                            </td>

                                        </tr>

                                    </table>

                                </td>
                            </tr>

                        </table>


                        <!-- Episode Cards -->

                        {episode_cards}


                        <!-- Footer -->

                        <table cellpadding="0"
                               cellspacing="0"
                               border="0"
                               width="100%"
                               style="padding: 16px 4px 4px 4px;">

                            <tr>

                                <td align="center"
                                    style="font-size: 12px;
                                           color: #9ca3af;">

                                    <a href="https://anilist.co/user/{anilist_user_escaped}/animelist"
                                       style="color: {accent_dark};
                                              text-decoration: none;
                                              font-weight: 600;">
                                        View your full AniList
                                    </a>

                                    <span style="margin: 0 6px;">·</span>

                                    Checked {checked_time} ({timezone_escaped})

                                    <span style="margin: 0 6px;">·</span>

                                    Next check in ~
                                    {self.poll_interval_seconds // 60} min

                                </td>

                            </tr>

                        </table>

                    </td>
                </tr>

            </table>

        </body>
        </html>
        """


    # ---- email ------------------------------------------------------------- #

    def send_email(
        self,
        episodes: list[dict],
        notification_type: str = "upcoming"
    ) -> bool:

        if not episodes:
            return False

        try:

            if notification_type == "release":
                subject = (
                    f"🎉 {len(episodes)} New Anime Episode"
                    f"{'s' if len(episodes) > 1 else ''} Released!"
                )
            else:
                subject = (
                    f"⏰ {len(episodes)} Anime Episode"
                    f"{'s' if len(episodes) > 1 else ''} Coming Soon"
                )

            msg = MIMEMultipart(
                "alternative"
            )

            msg["From"] = (
                f"{self.sender_name} "
                f"<{self.email_sender}>"
            )

            msg["To"] = self.email_receiver
            msg["Subject"] = subject

            text_lines = [
                f"Anime Episode Updates for {self.anilist_user}",
                "=" * 50,
                ""
            ]

            for ep in episodes:

                status = (
                    "Released Now!"
                    if notification_type == "release"
                    else f"Airing in: {ep['time_until']}"
                )

                text_lines += [
                    f"📺 {ep['title']}",
                    f"   Episode {ep['next_episode']}",
                    f"   Status: {status}",
                    f"   You've watched: Episode {ep['progress']}",
                    f"   Watch: {ep['url']}",
                    "─" * 40,
                ]

            text_lines += [
                "",
                "=" * 50,
                f"Check your full list: "
                f"https://anilist.co/user/{self.anilist_user}/animelist"
            ]

            text_body = "\n".join(
                text_lines
            )

            html_body = self.create_email_html(
                episodes,
                notification_type
            )

            msg.attach(
                MIMEText(
                    text_body,
                    "plain"
                )
            )

            msg.attach(
                MIMEText(
                    html_body,
                    "html"
                )
            )

            with smtplib.SMTP(
                self.smtp_server,
                self.smtp_port,
                timeout=30
            ) as server:

                server.starttls()

                server.login(
                    self.email_sender,
                    self.email_password
                )

                server.send_message(msg)

            self.logger.info(
                f"Email sent successfully "
                f"({notification_type}, "
                f"{len(episodes)} episode(s))"
            )

            return True

        except smtplib.SMTPException as e:

            self.logger.error(
                f"SMTP error sending email: {e}"
            )

            return False

        except OSError as e:

            self.logger.error(
                f"Network error sending email: {e}"
            )

            return False


    # ---- main cycle -------------------------------------------------------- #

    def check_and_notify(self) -> None:

        self.logger.info(
            "Checking AniList for updates..."
        )

        watching = self.get_watching_list()

        if not watching:

            self.logger.warning(
                "No currently-watching anime with "
                "upcoming episodes found "
                "(or the API call failed)."
            )

            return

        to_notify_upcoming = []
        to_notify_released = []

        for anime in watching:

            if anime.seconds_until is None:
                continue

            notify_key = (
                f"{anime.id}_{anime.next_episode}"
            )

            if anime.seconds_until <= 0:

                if (
                    anime.next_episode
                    and anime.next_episode > anime.progress
                ):

                    if notify_key not in self.state.get(
                        "notified_released",
                        []
                    ):

                        self.logger.info(
                            f"{anime.title}: "
                            f"Episode {anime.next_episode} "
                            f"is OUT NOW!"
                        )

                        to_notify_released.append(
                            self._episode_payload(
                                anime,
                                "Now!"
                            )
                        )

                        self.state.setdefault(
                            "notified_released",
                            []
                        ).append(
                            notify_key
                        )

            else:

                time_str = self.format_time(
                    anime.seconds_until
                )

                hours_until = (
                    anime.seconds_until / 3600
                )

                self.logger.info(
                    f"{anime.title}: "
                    f"Episode {anime.next_episode} "
                    f"in {time_str} "
                    f"(watched up to Ep "
                    f"{anime.progress})"
                )

                if hours_until <= self.hours_before_notify:

                    if notify_key not in self.state.get(
                        "notified_upcoming",
                        []
                    ):

                        to_notify_upcoming.append(
                            self._episode_payload(
                                anime,
                                time_str
                            )
                        )

                        self.state.setdefault(
                            "notified_upcoming",
                            []
                        ).append(
                            notify_key
                        )

        self._save_state()

        if to_notify_released:

            self.logger.info(
                f"Sending release notification for "
                f"{len(to_notify_released)} episode(s)..."
            )

            self.send_email(
                to_notify_released,
                "release"
            )

        if to_notify_upcoming:

            self.logger.info(
                f"Sending upcoming notification for "
                f"{len(to_notify_upcoming)} episode(s)..."
            )

            self.send_email(
                to_notify_upcoming,
                "upcoming"
            )

        if (
            not to_notify_released
            and not to_notify_upcoming
        ):
            self.logger.info(
                "No new episodes to notify about."
            )


    @staticmethod
    def _episode_payload(
        anime: AnimeEntry,
        time_until: str
    ) -> dict:

        return {
            "title": anime.title,
            "next_episode": anime.next_episode,
            "progress": anime.progress,
            "time_until": time_until,
            "url": anime.url,
            "cover": anime.cover,
            "description": anime.description,
            "score": anime.score,
            "genres": anime.genres,
            "total_episodes": anime.total_episodes,
        }


    def run_once(self) -> None:
        self.check_and_notify()


    def run(self) -> None:

        self.logger.info("=" * 60)
        self.logger.info(
            "Anime Episode Notifier starting"
        )
        self.logger.info(
            f"User: {self.anilist_user}"
        )
        self.logger.info(
            f"From: {self.sender_name} "
            f"<{self.email_sender}>  "
            f"To: {self.email_receiver}"
        )
        self.logger.info(
            f"Notify when within "
            f"{self.hours_before_notify}h of airing"
        )
        self.logger.info(
            f"Poll interval: "
            f"{self.poll_interval_seconds}s"
        )
        self.logger.info(
            f"Timezone: {self.timezone}"
        )
        self.logger.info("=" * 60)

        while not self._stop:

            try:
                self.check_and_notify()

            except Exception:
                self.logger.exception(
                    "Unexpected error during check cycle"
                )

            if self._stop:
                break

            self.logger.info(
                f"Sleeping for "
                f"{self.poll_interval_seconds}s..."
            )

            slept = 0

            while (
                slept < self.poll_interval_seconds
                and not self._stop
            ):

                time.sleep(
                    min(
                        5,
                        self.poll_interval_seconds - slept
                    )
                )

                slept += 5

        self.logger.info("Stopped.")


def main() -> None:

    parser = argparse.ArgumentParser(
        description="AniList episode notifier"
    )

    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config.json"
    )

    parser.add_argument(
        "--state",
        default="anilist_state.json",
        help="Path to state file"
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check and exit (good for cron)"
    )

    args = parser.parse_args()

    try:

        notifier = AniListNotifier(
            args.config,
            args.state
        )

    except ConfigError as e:

        print(
            f"Config error: {e}",
            file=sys.stderr
        )

        sys.exit(1)

    if args.once:
        notifier.run_once()
    else:
        notifier.run()


if __name__ == "__main__":
    main()
