# News Digest Bot

This Python script fetches the latest Google News RSS headlines for a user-supplied list of topics and sends a nicely formatted email digest via Gmail. It prioritizes high-importance headlines using keyword-based scoring and ensures that each email contains fresh, non-repeating articles. Designed to run daily using `cron` on any Unix-based system.

## 📁 Directory Structure
```plaintext
digest-bot/
├── digest_bot.py         # Main script
├── topics.csv            # List of topics (one per line)
├── last_seen.json        # Tracks all previously sent articles
├── logs/
│   └── digest.log        # Cron + runtime logs
```

## ⚙️ Setup

1. **Clone or upload the project** to your server.

2. **Edit `topics.csv` with your desired topics:**  
   Example:
   ```
   Apple
   AI Safety
   Climate Change
   ```

3. **Add Gmail credentials to your `~/.bash_profile`:**

   *(Requires 2FA and a [Gmail App Password](https://support.google.com/accounts/answer/185833))*

   ```bash
   export GMAIL_USER="your_email@gmail.com"
   export GMAIL_APP_PASSWORD="your_app_password"
   export MAILTO="recipient_email@example.com"
   ```

   Then apply changes:
   ```bash
   source ~/.bash_profile
   ```

4. **Run the script manually to test:**
   ```bash
   python3 -W ignore digest_bot.py
   ```

   You should receive your digest within a few minutes.

---

## ⏱️ Automate with Cron

To send your digest every day at **8:00 AM**, add this to your crontab:

```bash
crontab -e
```

Then insert:
```bash
0 8 * * * cd ~/digest-bot && /usr/bin/env bash -c 'source ~/.bash_profile && /usr/bin/env python3 -W ignore digest_bot.py' >> ~/digest-bot/logs/digest.log 2>&1
```
*(Note: this means 8AM for the machine this is running on.)*

---

## 💡 Features

- **Smart headline selection** based on a keyword scoring system
- **Stemming and lemmatization** for robust keyword matching
- **Only one high-priority headline per topic** in each email
- **De-duplication across runs**: avoids repeating the same or similar headlines
- **Full historical tracking**: remembers all previously sent articles
- **Localizes timestamps** to Eastern Time (ET)
- **HTML-formatted digest with clickable links**
- **Lockfile** to prevent overlapping runs
- **Cron + log support** for automation and monitoring