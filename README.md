# 🎬 AniList Anime Notifier

A lightweight Python anime episode notifier that monitors your **AniList Currently Watching** list and sends email notifications when episodes are approaching or have been released.

The notifier is designed to run automatically using **GitHub Actions**, so your computer does not need to stay online.

---

## ✨ Features

- 📺 Monitors your AniList **Currently Watching** list
- ⏰ Notifies you about upcoming episodes
- 🎉 Notifies you when episodes are released
- 📧 Sends formatted HTML email notifications
- 🖼️ Includes anime cover images
- ⭐ Shows AniList scores
- 🎭 Shows genres
- 📊 Shows total episode count
- 🔗 Includes AniList links
- 💾 Stores notification state between runs
- 🚫 Prevents duplicate notifications
- 🔄 Automatically saves state back to GitHub
- ⏱️ Runs automatically every hour
- ▶️ Supports manual execution
- 🔁 Includes a manual state-reset workflow
- 🛡️ Uses HTTP retries, backoff, and timeouts
- 📝 Provides console and rotating file logging
- 🧹 Limits state-file growth
- 🛑 Handles graceful shutdown
- 💻 Can be run locally
- 🌐 Uses the AniList GraphQL API
- 💸 Can be hosted for free using GitHub Actions

---

## 📋 How It Works

```text
                    GitHub Actions
                          │
                    Every hour
                          │
                          ▼
                 Checkout repository
                          │
                          ▼
                  Setup Python 3.13
                          │
                          ▼
                 Install dependencies
                          │
                          ▼
              Create temporary config
                  from GitHub Secrets
                          │
                          ▼
             Run anilist_notifier.py
                      --once
                          │
                          ▼
                    Query AniList
                          │
                          ▼
                 Check episode status
                    ┌─────┴─────┐
                    ▼           ▼
                Upcoming     Released
                    │           │
                    └─────┬─────┘
                          ▼
                    Send email
                          │
                          ▼
                 Update state file
                          │
                          ▼
                  Commit + push
```

Your computer does **not** need to remain online.

---

# 🚀 Setup

## 1. Fork the Repository

Click **Fork** at the top of this repository.

Each user should use their own copy because the notifier uses a personal AniList account, email configuration, and notification state.

---

## 2. Add GitHub Secrets

Go to:

**Repository → Settings → Secrets and variables → Actions → Secrets**

Add the following repository secrets:

| Secret | Description |
|---|---|
| `ANILIST_NOTIFIER_EMAIL` | Email address used to send notifications |
| `ANILIST_NOTIFIER_RECEIVER` | Email address that receives notifications |
| `ANILIST_NOTIFIER_ANILIST_USERNAME` | Your AniList username |
| `ANILIST_NOTIFIER_SMTP_PASSWORD` | Gmail SMTP/App Password |

### Example

```text
ANILIST_NOTIFIER_EMAIL
your-email@gmail.com

ANILIST_NOTIFIER_RECEIVER
receiver@example.com

ANILIST_NOTIFIER_ANILIST_USERNAME
your_anilist_username

ANILIST_NOTIFIER_SMTP_PASSWORD
your_gmail_app_password
```

> **An AniList API token is not required by the current implementation.**

> Never commit your email password, App Password, or other credentials to the repository.

---

# 📺 AniList Setup

The notifier uses your AniList username to access your **Currently Watching** list.

Set:

```text
ANILIST_NOTIFIER_ANILIST_USERNAME
```

to your AniList username.

For example:

```text
mustakim
```

The current implementation does **not require an AniList API token**.

---

# 📧 Gmail Setup

The notifier currently uses Gmail SMTP.

```text
SMTP Server: smtp.gmail.com
SMTP Port:   587
Security:    STARTTLS
```

For Gmail, use a **Google App Password** rather than your normal Google account password.

Store the App Password as:

```text
ANILIST_NOTIFIER_SMTP_PASSWORD
```

---

# ⚙️ Configuration

The GitHub Actions workflow creates `config.json` automatically during each run.

Credentials are supplied through GitHub Secrets rather than being permanently stored in the repository.

The generated configuration contains settings similar to:

```json
{
    "email": {
        "sender": "your-email@gmail.com",
        "receiver": "receiver@example.com",
        "sender_name": "Anime Notifier",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587
    },
    "anilist": {
        "username": "your_anilist_username"
    },
    "check_interval": 3600,
    "notify_before_release": true,
    "hours_before_notify": 24,
    "notify_after_release": true
}
```

---

# ⏰ Automatic Schedule

The GitHub Actions workflow uses:

```yaml
on:
  schedule:
    - cron: "17 * * * *"
```

This runs the notifier approximately **once every hour at 17 minutes past the hour**.

For example:

```text
01:17
02:17
03:17
04:17
05:17
...
```

GitHub Actions scheduling can experience delays, so it should not be considered an exact-to-the-second scheduler.

---

# ▶️ Manual Run

You can manually run the notifier without waiting for the next scheduled execution.

1. Open your GitHub repository.
2. Go to **Actions**.
3. Select **Anime Notifier**.
4. Click **Run workflow**.
5. Select the `main` branch.
6. Click **Run workflow**.

The workflow performs a single check.

---

# 💾 Notification State

The notifier uses:

```text
anilist_state.json
```

to remember which notifications have already been sent.

This prevents the same episode from generating duplicate emails during subsequent hourly checks.

After a successful run, the workflow checks whether the state has changed.

If it has changed, GitHub Actions commits and pushes the updated state.

---

# 🔄 Reset Notification State

The project includes a separate workflow for resetting notification history.

To reset:

1. Open **GitHub → Actions**.
2. Select **Reset Anime State**.
3. Click **Run workflow**.
4. Select `main`.
5. Click **Run workflow**.

The reset workflow runs:

```bash
python reset_state.py
```

After the reset, the notifier starts with a fresh notification state.

---

# 🗂️ Project Structure

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
```

### Files

| File | Purpose |
|---|---|
| `anilist_notifier.py` | Main notifier program |
| `anilist_state.json` | Stores notification state |
| `reset_state.py` | Resets notification state |
| `requirements.txt` | Python dependencies |
| `anime-notifier.yml` | Automatic/manual notifier workflow |
| `reset-state.yml` | Manual state-reset workflow |
| `.gitignore` | Prevents unnecessary files from being committed |
| `README.md` | Project documentation |

---

# 🔐 Security

Credentials should be stored using **GitHub Secrets**.

Do not commit sensitive information to the repository.

Especially keep the following private:

```text
ANILIST_NOTIFIER_SMTP_PASSWORD
```

Email addresses and the AniList username can also be kept in Secrets rather than exposed in the repository.

---

# 📝 Recommended `.gitignore`

```gitignore
__pycache__/
*.pyc
anilist_notifier.log
config.json
```

This prevents generated files and local configuration from being committed unnecessarily.

---

# 🧪 Run Locally

The notifier can also be run directly on your computer.

## Install dependencies

```bash
pip install -r requirements.txt
```

## Run once

```bash
python anilist_notifier.py --once
```

`--once` performs one check and then exits.

## Run continuously

```bash
python anilist_notifier.py
```

Without `--once`, the program can continue running according to its configured polling interval.

---

# 📧 Email Notifications

## ⏰ Upcoming Episodes

Upcoming episode emails can contain:

- Anime title
- Episode number
- Time until airing
- Cover image
- Genres
- AniList score
- Total episode count
- Description
- AniList link

---

## 🎉 Released Episodes

Release notifications indicate that an episode has been released and provide an AniList link.

---

# 🌏 Time Zone

The application can display timestamps using the configured local timezone.

The current setup is intended to display times in:

```text
Asia/Dhaka
```

---

# 🔁 GitHub Actions Concurrency

The workflow uses:

```yaml
concurrency:
  group: anime-notifier
  cancel-in-progress: false
```

This prevents multiple notifier jobs from running simultaneously.

This is important because the workflow modifies:

```text
anilist_state.json
```

and pushes the updated state back to the repository.

---

# 🛡️ Reliability

The notifier includes:

- HTTP retries
- Exponential backoff
- Request timeouts
- AniList GraphQL error detection
- Invalid JSON handling
- Configuration validation
- SMTP password validation
- Graceful shutdown
- Rotating log files
- State-file size limiting

These features help the notifier handle temporary network and API problems.

---

# 📝 Logging

The notifier provides console logging and writes to:

```text
anilist_notifier.log
```

The log uses a rotating file handler so it does not grow indefinitely.

The log file should normally remain excluded from Git using `.gitignore`.

---

# 💰 Hosting

The project can run completely free using **GitHub Actions**.

You do not need:

- ❌ VPS
- ❌ Paid background worker
- ❌ Dedicated server
- ❌ Raspberry Pi
- ❌ Always-on computer

GitHub runs the notifier according to the workflow schedule.

---

# 👥 Using the Project for Other Users

The recommended way for other people to use the project is to **fork the repository**.

Each user gets their own independent setup:

```text
                 Original Repository
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
           User A      User B      User C
              │          │          │
           Secrets    Secrets    Secrets
              │          │          │
           AniList    AniList    AniList
              │          │          │
           State A    State B    State C
```

Each user provides their own:

- AniList username
- Sender email
- Receiver email
- Gmail App Password

No user needs access to another user's credentials or notification state.

---

# 🧭 User Setup Summary

```text
1. Fork repository
        ↓
2. Add GitHub Secrets
        ↓
3. Enable GitHub Actions
        ↓
4. Run Anime Notifier manually
        ↓
5. Check email
        ↓
6. Done
        ↓
GitHub Actions runs automatically every hour
```

---

# 🛠️ Troubleshooting

## Workflow is not appearing

Make sure the workflow files are located inside:

```text
.github/workflows/
```

and use the `.yml` extension.

---

## Workflow fails because of missing secrets

Go to:

**Settings → Secrets and variables → Actions**

Make sure these names exactly match:

```text
ANILIST_NOTIFIER_EMAIL
ANILIST_NOTIFIER_RECEIVER
ANILIST_NOTIFIER_ANILIST_USERNAME
ANILIST_NOTIFIER_SMTP_PASSWORD
```

---

## No email received

Check:

1. The GitHub Actions run completed successfully.
2. The workflow logs for errors.
3. Your email spam/junk folder.
4. Your Gmail App Password.
5. The sender and receiver secrets.

---

## Duplicate notifications

The notification history is stored in:

```text
anilist_state.json
```

If necessary, use the **Reset Anime State** workflow.

---

## State push fails

The workflow saves the state back to the repository after the notifier runs.

It uses Git operations such as:

```bash
git pull --rebase --autostash origin main
git push origin main
```

to reduce the chance of conflicts when updating the state file.

---

# 📦 Dependencies

Python dependencies are listed in:

```text
requirements.txt
```

Install them with:

```bash
pip install -r requirements.txt
```

---

# 📜 License

This project is provided for personal and educational use.

Feel free to fork, modify, and adapt it for your own needs.
