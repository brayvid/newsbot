# News Digest Bot

This Python script fetches the latest Google News RSS headlines for a curated list of topics and sends a nicely formatted email digest via Gmail. It uses both a keyword scoring system and topic criticality from a CSV file, and intelligently boosts relevance using **trending topics** from a free news API. It ensures each email contains timely, non-repeating, high-priority articles. Designed to run daily using `cron` on any Unix-based system.

---

## 📁 Directory Structure

```plaintext
digest-bot/
├── digest_bot.py         # Main script
├── scored_topics.csv     # Topics and their criticality scores
├── last_seen.json        # Tracks all previously sent articles (not committed)
├── .env                  # Email + API credentials (not committed)
├── logs/                 # Logs folder (not committed)
│   └── digest_bot.log    # Cron + runtime logs (not committed)
```

---

## ⚙️ Setup

### 1. Clone or upload the project to your server

---

### 2. Install dependencies

```bash
pip3 install -r requirements.txt
```

Or manually:

```bash
pip3 install nltk requests python-dotenv
```

---

### 3. Create a `.env` file with credentials

```env
GMAIL_USER=your_email@gmail.com
GMAIL_APP_PASSWORD=your_app_password
MAILTO=recipient@example.com
NEWSDATA_API_KEY=your_newsdata_api_key
```

- You must [enable 2FA](https://myaccount.google.com/security) and [generate an App Password](https://support.google.com/accounts/answer/185833) for Gmail.
- Get a free API key from [newsdata.io](https://newsdata.io/).

✅ `.env` is automatically loaded by the script.  
✅ `.env` is excluded from version control via `.gitignore`.

---

### 4. Run the script manually to test

```bash
python3 -W ignore digest_bot.py
```

You should receive your digest email shortly.

---

## ⏱️ Automate with Cron

To run the script every day at **8:00 AM**, add an entry to your crontab:

```bash
crontab -e
```

Add:

```bash
0 8 * * * cd ~/news-digest-bot && /usr/bin/env python3 -W ignore digest_bot.py >> ~/news-digest-bot/logs/digest_bot.log 2>&1
```
This will run daily at 8AM server time.

---

## 💡 Features

- **Trending awareness**: Relevance is boosted for topics matching today’s trending headlines (via `newsdata.io`)
- **Topic importance scoring** from `scored_topics.csv`
- **Headline relevance scoring** using tiered keywords
- **Stemming + lemmatization** for smarter keyword matching
- **Only includes articles with high combined scores (≥ 20)**
- **No repetition**: Remembers previously sent articles
- **Nicely formatted HTML email** with clickable links
- **Lockfile** ensures no duplicate cron runs
- **`.env` support** for Gmail and API credentials

---