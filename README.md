# AniList Episode Notifier

A Python-based notifier that watches your AniList "Currently Watching" list and sends email notifications when new episodes are about to air or have just been released.

## Features

- 📺 **Automatic Monitoring**: Watches your AniList "Currently Watching" list for upcoming and recently released episodes
- 📧 **Email Notifications**: Sends formatted HTML emails with anime details, including cover images, descriptions, and episode information
- 🔄 **State Persistence**: Tracks which episodes have been notified to avoid duplicate alerts
- 🛡️ **Robust Error Handling**: Handles network issues, rate limiting, and API errors gracefully
- 🔐 **Secure Configuration**: Supports environment variables for sensitive data like SMTP passwords
- 🚀 **GitHub Actions Ready**: Includes workflows for automated scheduling and state management
- 📝 **Comprehensive Logging**: Console output + rotating file logs for debugging and monitoring
- 🌍 **Configurable Timezone**: Set your local timezone for accurate timestamps in emails

## Prerequisites

- Python 3.13 or higher
- AniList account with a public username
- Email account with SMTP access (Gmail recommended)
- GitHub account (for automated deployment)

## Installation

### Local Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/anilist-notifier.git   # replace with your own repo URL
cd anilist-notifier
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `config.json` file in the project root with the following structure:
```json
{
    "email": {
        "sender": "your-email@gmail.com",
        "receiver": "receiver-email@gmail.com",
        "sender_name": "Anime Notifier",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587
    },
    "anilist": {
        "username": "your-anilist-username",
        "token": "your-anilist-token"
    },
    "timezone": "Asia/Dhaka",
    "check_interval": 3600,
    "notify_before_release": true,
    "hours_before_notify": 24,
    "notify_after_release": true
}
```

> **Important**: 
> - Do **not** store your SMTP password in `config.json`. Instead, set the environment variable `ANILIST_NOTIFIER_SMTP_PASSWORD` (see step 4).
> - Set your correct timezone (see the Timezone Configuration section below).

4. Set the SMTP password as an environment variable:

**Linux/macOS:**
```bash
export ANILIST_NOTIFIER_SMTP_PASSWORD="your-app-password"
```

**Windows (Command Prompt):**
```cmd
set ANILIST_NOTIFIER_SMTP_PASSWORD="your-app-password"
```

**Windows (PowerShell):**
```powershell
$env:ANILIST_NOTIFIER_SMTP_PASSWORD="your-app-password"
```

### Running Locally

```bash
# Single check (useful for cron or systemd timers)
python anilist_notifier.py --once

# Continuous monitoring (runs indefinitely, checking every `check_interval` seconds)
python anilist_notifier.py
```

## Timezone Configuration

The notifier uses your local timezone for timestamps in emails. Add the `timezone` field to your `config.json`:

```json
{
    "timezone": "Asia/Dhaka"
}
```

Common timezone values:

| Region | Timezone Value |
|--------|---------------|
| Bangladesh | `Asia/Dhaka` |
| USA (Eastern) | `America/New_York` |
| USA (Pacific) | `America/Los_Angeles` |
| UK | `Europe/London` |
| India | `Asia/Kolkata` |
| Japan | `Asia/Tokyo` |
| Australia (Sydney) | `Australia/Sydney` |
| Germany | `Europe/Berlin` |
| Singapore | `Asia/Singapore` |

If no timezone is specified, it defaults to `UTC`.

## Logging

The notifier writes logs to both the console and a file:

- **Log file**: `anilist_notifier.log` (created in the same directory as the script)
- **Rotation**: Each log file is capped at 1 MB; up to 3 backup files are kept (`anilist_notifier.log.1`, `.log.2`, `.log.3`)
- **Format**: Timestamp, log level, and message (e.g., `2025-03-21 10:15:30 [INFO] Fetched watching list`)

If you don't see the log file being updated, check:
- The script has write permissions to the current directory.
- The script is actually running (check console output).
- The log file might be locked by another process (rare).

In GitHub Actions runs, the log file is ephemeral—it exists only during the job and is not preserved unless you upload it as an artifact.

## GitHub Actions Deployment

### Setting Up

1. Fork this repository to your GitHub account.

2. Add the following secrets to your repository (Settings → Secrets and Variables → Actions):
   - `ANILIST_NOTIFIER_EMAIL`: Your email address (sender)
   - `ANILIST_NOTIFIER_RECEIVER`: The email address to receive notifications
   - `ANILIST_NOTIFIER_ANILIST_USERNAME`: Your AniList username
   - `ANILIST_NOTIFIER_ANILIST_TOKEN`: Your AniList API token (optional)
   - `ANILIST_NOTIFIER_SMTP_PASSWORD`: Your email app password

3. The workflow will automatically:
   - Run every hour (at the 17th minute)
   - Check for new episodes
   - Send email notifications if needed
   - Save the state back to the repository

### Manual Workflow Triggers

You can manually trigger the workflow from GitHub Actions:
1. Go to Actions tab in your repository
2. Select "Anime Notifier" workflow
3. Click "Run workflow"

## How It Works

1. **Monitoring**: The script queries the AniList GraphQL API for your "Currently Watching" list.

2. **Episode Detection**: For each anime, it checks:
   - If the next episode is airing soon (within `hours_before_notify` window)
   - If a new episode has been released since the last check

3. **State Management**: The script maintains a state file (`anilist_state.json`) that tracks:
   - `notified_upcoming`: Episodes that have been notified as upcoming
   - `notified_released`: Episodes that have been notified as released

4. **Email Notifications**: Sends a formatted HTML email with:
   - Anime title and episode number
   - Cover image
   - Description (HTML-safe)
   - Genres and score
   - Direct link to the anime on AniList
   - Local timezone timestamp

5. **State Persistence**: After each check, the state is saved back to the repository via GitHub Actions.

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `timezone` | Your local timezone (e.g., `Asia/Dhaka`, `America/New_York`) | `UTC` |
| `check_interval` | Seconds between checks in continuous mode | 3600 |
| `hours_before_notify` | Hours before airing to send upcoming notification | 24 |
| `notify_before_release` | Enable/disable upcoming episode notifications | true |
| `notify_after_release` | Enable/disable released episode notifications | true |
| `poll_interval_seconds` | Override for check interval | 3600 |

## Email Configuration

For Gmail users:
1. Enable 2-factor authentication on your Google account
2. Generate an app password:
   - Go to Google Account → Security → 2-Step Verification → App passwords
   - Select "Mail" and "Other" (name it "AniList Notifier")
   - Copy the generated 16-character password
   - Use this password as the `ANILIST_NOTIFIER_SMTP_PASSWORD` environment variable

For other SMTP providers:
- Adjust `smtp_server` and `smtp_port` accordingly
- Use appropriate authentication method

## Troubleshooting

### Common Issues

1. **"Config file not found"**
   - Ensure `config.json` exists in the project directory

2. **"No SMTP password found"**
   - Set `ANILIST_NOTIFIER_SMTP_PASSWORD` environment variable
   - Or add `password` field to `email` section in config (not recommended for security)

3. **"Timezone not found"**
   - Check that your timezone is correct (e.g., `Asia/Dhaka`, not `Asia/Dhaka ` with a space)
   - Install `tzdata`: `pip install tzdata`
   - If the timezone is invalid, it will fall back to `UTC`

4. **"AniList GraphQL error"**
   - Verify your AniList username is correct
   - Check if your list is public
   - Ensure you have "Currently Watching" items

5. **"Network error contacting AniList"**
   - Check your internet connection
   - The API might be temporarily unavailable
   - Rate limiting might be active

### State File Issues

If the state file gets corrupted, delete `anilist_state.json` and run the script again. The state will be regenerated.

### Resetting State

Use the "Reset Anime State" workflow in GitHub Actions to clear the notification state:
1. Go to Actions tab
2. Select "Reset Anime State"
3. Click "Run workflow"

## Development

### Project Structure

```
anilist-notifier/
├── .github/
│   └── workflows/
│       ├── anime-notifier.yml
│       └── reset-state.yml
├── anilist_notifier.py
├── anilist_state.json          (auto‑generated)
├── reset_state.py
├── requirements.txt
├── README.md
└── .gitignore
```

### Adding Features

To extend the notifier:

1. Modify the GraphQL query in `anilist_notifier.py` to fetch additional fields
2. Update the `AnimeEntry` dataclass to include new fields
3. Modify the email template in `_build_email_content()` to display new information
4. Update the state management logic if adding new notification types

## Security Notes

- Never commit `config.json` containing passwords to version control
- Use environment variables for sensitive data in production
- The `.gitignore` file excludes `config.json` by default
- HTML content is escaped to prevent email injection attacks

## Dependencies

- `requests` – HTTP client for API calls
- `urllib3` – HTTP client utilities
- `tzdata` – Timezone database support (required for timezone formatting)

## License

This project is open source. Feel free to modify and use it as you wish.

## Acknowledgments

- Built with [AniList API](https://anilist.gitbook.io/anilist-apiv2-docs/)
- Uses [Requests library](https://requests.readthedocs.io/) for HTTP requests
- Designed for GitHub Actions automation

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

For issues, bug reports, or feature requests, please use the GitHub Issues section of the repository.
