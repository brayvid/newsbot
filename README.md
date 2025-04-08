# News Digest Bot

This Python script fetches the latest Google News RSS headlines for a user-supplied list of topics and sends a nicely formatted email digest via Gmail. It uses both topic-level criticality and keyword-based scoring to prioritize the most important headlines and ensures each email includes only fresh, high-priority articles. Designed to run daily via `cron` on any Unix-based system.

---

## 📁 Directory Structure
```plaintext
digest-bot/
├── digest_bot.py           # Main script
├── scored_topics.csv       # List of topics + criticality score (1–5)
├── last_seen.json          # Tracks all previously sent articles
├── logs/
│   └── digest.log          # Cron + runtime logs
```

---

## ⚙️ Setup

1. **Clone or upload the project** to your server.

2. **Edit `scored_topics.csv` with your desired topics and scores:**  
   Format:
   ```csv
   Artificial Intelligence,5
   Climate Change,4
   Mars,2
   ...
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

To send your digest every day at **8:00 AM** (server time), add this to your crontab:

```bash
crontab -e
```

Then insert:
```bash
0 8 * * * cd ~/digest-bot && /usr/bin/env bash -c 'source ~/.bash_profile && /usr/bin/env python3 -W ignore digest_bot.py' >> ~/digest-bot/logs/digest.log 2>&1
```

---

## 💡 Features

- **Headline scoring combines keyword relevance × topic criticality**
- **Stemming and lemmatization** for better keyword matching
- **Only includes headlines with combined score ≥ 20**
- **One top headline per topic** per email
- **De-duplicates similar headlines within and across runs**
- **Remembers all previously sent articles across history**
- **Fully HTML-formatted digest with clickable links**
- **Lockfile** to prevent overlapping runs
- **Cron + log support** for automation and monitoring