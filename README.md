# AniList Episode Notifier

A Python-based notifier that watches your AniList "Currently Watching" list and sends email notifications when new episodes are about to air or have just been released.

## Features

- 📺 **Automatic Monitoring**: Watches your AniList "Currently Watching" list for upcoming and recently released episodes
- 📧 **Email Notifications**: Sends formatted HTML emails with anime details, including cover images, descriptions, and episode information
- 🔄 **State Persistence**: Tracks which episodes have been notified to avoid duplicate alerts
- 🛡️ **Robust Error Handling**: Handles network issues, rate limiting, and API errors gracefully
- 🔐 **Secure Configuration**: Supports environment variables for sensitive data like SMTP passwords
- 🚀 **GitHub Actions Ready**: Includes workflows for automated scheduling and state management
- 📝 **Comprehensive Logging**: Console and file logging with rotation for debugging and monitoring

## Prerequisites

- Python 3.13 or higher
- AniList account with a public username
- Email account with SMTP access (Gmail recommended)
- GitHub account (for automated deployment)

## Installation

### Local Setup

1. Clone the repository:
```bash
git clone https://github.com/notmustakim/Anime-Notifier.git
cd Anime-Notifier
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
        "token": "your-anilist-token"   // optional, not currently used
    },
    "check_interval": 3600,
    "notify_before_release": true,
    "hours_before_notify": 24,
    "notify_after_release": true
}
```

> **Note**: The `password` field is **not** stored in the config file for security. Instead, set the environment variable `ANILIST_NOTIFIER_SMTP_PASSWORD` (see step 4).

4. Set the SMTP password as an environment variable (recommended):
```bash
export ANILIST_NOTIFIER_SMTP_PASSWORD="your-app-password"
```
   (For Windows, use `set` instead of `export`.)

### Running Locally

```bash
# Single check (useful for cron or systemd timers)
python anilist_notifier.py --once

# Continuous monitoring (runs indefinitely, checking every `check_interval` seconds)
python anilist_notifier.py
```

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

5. **State Persistence**: After each check, the state is saved back to the repository via GitHub Actions.

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `check_interval` | Seconds between checks in continuous mode | 3600 |
| `hours_before_notify` | Hours before airing to send upcoming notification | 24 |
| `notify_before_release` | Enable/disable upcoming episode notifications | true |
| `notify_after_release` | Enable/disable released episode notifications | true |
| `poll_interval_seconds` | Override for check interval (if you want to change it without editing config) | 3600 |

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

3. **"AniList GraphQL error"**
   - Verify your AniList username is correct
   - Check if your list is public
   - Ensure you have "Currently Watching" items

4. **"Network error contacting AniList"**
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
