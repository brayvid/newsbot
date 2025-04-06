# Digest Bot

This Python script fetches the latest RSS headlines for a list of topics and sends a nicely formatted email digest with Gmail. It uses Google News RSS feeds and can be scheduled via `cron` on any Unix-based system.

## Directory Structure
```plaintext
digest-bot/
├── digest_bot.py         # Main script
├── topics.csv            # List of topics (one per line)
├── last_seen.json        # Tracks last sent article per topic
├── logs/
│   └── digest.log        # Cron + runtime logs
```
## Setup

1. **Clone/upload the project** to your server.

2. **Modify `topics.csv` to your liking:**  
   Example:
   ```
   Apple
   AI Safety
   Climate Change
   ```


3. **Add Gmail credentials to your `~/.bash_profile`:**

   (You must [create an App Password](https://support.google.com/accounts/answer/185833) from your Gmail account settings and have 2FA enabled.)

   ```bash
   export GMAIL_USER="your_email@gmail.com"
   export GMAIL_APP_PASSWORD="your_app_password"
   export MAILTO="recipient_email@example.com"
   ```

   Then run:

   ```bash
   source ~/.bash_profile
   ```

4. **Test the script:**
   ```bash
   python3 digest_bot.py
   ```

   You should receive your email digest within a few minutes.



## Set up Cron
To send the latest digest every day at **8:00 AM**, run:

```bash
crontab -e
```

Then add:

```bash
0 8 * * * cd ~/digest-bot && /usr/bin/env bash -c 'source ~/.bash_profile && /usr/bin/env python3 -W ignore digest_bot.py' >> ~/digest-bot/logs/digest.log 2>&1
```



## Features
- Digests only include topics with new articles
- Fully HTML-formatted clickable email
- Uses `User-Agent` headers for reliable RSS fetching
- Lockfile prevents overlapping runs