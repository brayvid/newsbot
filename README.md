# News Digest Bot

This Python script fetches the latest Google News RSS headlines for a user-supplied list of topics and sends a nicely formatted email digest via Gmail. It prioritizes high-importance headlines using keyword and topic scoring, and ensures each email contains fresh, non-repeating articles. Designed to run daily using `cron` on any Unix-based system.

---

## 📁 Directory Structure

```plaintext
digest-bot/
├── digest_bot.py         # Main script
├── scored_topics.csv     # Topics and their criticality scores
├── last_seen.json        # Tracks all previously sent articles (not committed)
├── .env                  # Email credentials (not committed)
├── logs/                 # Logs folder (not committed)
│   └── digest.log        # Cron + runtime logs (not committed)
```

---

## ⚙️ Setup

### 1. Clone or upload the project to your server

---

### 2. Install dependencies

Make sure you have the following installed:

```bash
pip3 install -r requirements.txt
```

**Or manually:**

```bash
pip3 install dotenv nltk requests
```

---

### 3. Add your Gmail credentials to a `.env` file

Create a file named `.env` in the project directory:

```env
GMAIL_USER=your_email@gmail.com
GMAIL_APP_PASSWORD=your_app_password
MAILTO=recipient@example.com
```

⚠️ You must [enable 2FA](https://myaccount.google.com/security) and [generate an App Password](https://support.google.com/accounts/answer/185833) for your Gmail account.

**Important:**  
Add `.env` to your `.gitignore` file to prevent accidentally committing it.

---

### 4. Run the script manually to test

```bash
python3 -W ignore digest_bot.py
```

You should receive a formatted digest in your inbox shortly.

---

## ⏱️ Automate with Cron

To send your digest every day at **8:00 AM**, add an entry to your crontab:

```bash
crontab -e
```

Then insert and save:

```bash
0 8 * * * cd ~/digest-bot && /usr/bin/env python3 -W ignore digest_bot.py >> ~/digest-bot/logs/digest_bot.log 2>&1
```

This will run daily at 8AM server time.

---

## 💡 Features

- **Topic importance scoring** (via `scored_topics.csv`)
- **Headline relevance scoring** using robust keyword matching
- **Stemming + lemmatization** for smarter text comparison
- **Only sends high-priority headlines** (score ≥ 20)
- **De-duplication**: avoids repeating articles across runs
- **HTML-formatted digest with clickable headlines**
- **Lockfile** prevents overlapping runs
- **`.env` + `dotenv` support** for safe credential storage