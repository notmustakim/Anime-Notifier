# 🎬 AniList Anime Notifier

A Python-based anime episode notifier that watches your **AniList Currently Watching list** and sends email notifications when new episodes are about to air or have been released.

The notifier can run automatically using **GitHub Actions**, so no computer or server needs to stay online.

---

## ✨ Features

- 📺 Monitors your AniList **Currently Watching** list
- ⏰ Checks for upcoming anime episodes
- 🎉 Notifies when new episodes are released
- 📧 Sends HTML-formatted email notifications
- 🖼️ Includes anime cover images
- ⭐ Shows AniList scores
- 🎭 Shows genres
- 📊 Shows total episode count
- 🔗 Provides links to AniList
- 🔐 Keeps credentials in GitHub Secrets
- 💾 Maintains notification state to avoid duplicate notifications
- 🔄 Automatically saves state back to the repository
- 🛡️ Uses HTTP retries and timeouts
- 📝 Provides console and rotating file logging
- ⚙️ Validates configuration on startup
- 🧹 Prevents the state file from growing indefinitely
- 🛑 Handles graceful shutdown
- ▶️ Supports one-time execution with `--once`
- 🔁 Runs automatically every hour through GitHub Actions
- 🔧 Includes a manual state-reset workflow

---

## 🗂️ Project Structure

```text
Anime-Notifier/
│
├── .github/
│   └── workflows/
│       ├── anime-notifier.yml
│       └── reset-state.yml
│
├── anilist_notifier.py
├── anilist_state.json
├── reset_state.py
├── requirements.txt
├── README.md
└── .gitignore
