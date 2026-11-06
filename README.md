# NewsBot

This Python script fetches the latest Google News RSS headlines for a user-supplied list of topics and sends a nicely formatted email digest. It uses Google Gemini to prioritize headlines and avoid duplicates with a history file. Designed to run daily using `cron` on any Unix-based system.

---

## How it works

- Reads [this configuration file](https://docs.google.com/spreadsheets/d/1OjpsQEnrNwcXEWYuPskGRA5Jf-U8e_x0x3j2CKJualg/edit?usp=sharing) on Google Sheets with user topics, keywords, overrides and script parameters
- Retrieves the latest headlines for all your topics from Google News RSS
- Applies stemming and lemmatization to headlines and eliminates duplicates
- Queries Gemini to prioritize remaining headlines according to your preferences
- Sends you a clean HTML email digest
- Schedule with `cron`

---

## Directory Structure

```plaintext
newsbot/
├── newsbot.py            # Main digest script
├── prune_history.py      # History pruner script
├── requirements.txt      # Package requirements
├── history.json          # Tracks previously sent headlines
├── .env                  # Credentials and configuration (excluded from git)
├── .venv/                # Python virtual environment (excluded from git)
└── logs/                 # Logging directory (excluded from git)
    ├── newsbot.log       # Main runtime logs
    └── prune_history.log # History prune logs
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/brayvid/newsbot.git
cd newsbot
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

With your virtual environment activated:

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install nltk requests python-dotenv google-genai
```

### 4. Prepare environment file

Create `.env`:

```bash
nano .env
```

Add your credentials, recipient(s), Gemini API key, and optional GitHub sync credentials:

```env
GMAIL_USER=your_email@gmail.com
GMAIL_APP_PASSWORD=your_app_password
MAILTO=recipient1@example.com,recipient2@example.com
GEMINI_API_KEY=your_gemini_api_key

# Optional: Needed if ENABLE_GIT_PUSH is enabled
GITHUB_USER=your_github_username
GITHUB_TOKEN=ghp_your_github_pat_token
GITHUB_REPOSITORY=username/newsbot
```

You must [enable 2FA](https://myaccount.google.com/security) and [generate an App Password](https://support.google.com/accounts/answer/185833) for your Gmail account, and [generate a Gemini API Key](https://ai.google.dev/gemini-api/docs/api-key).

### 5. Specify preferences

**Make a copy of your configuration sheet, publish each tab as a CSV, and update the URLs at the top of `newsbot.py`.**
  
#### Topics (scored 1-5)

```csv
Topic,Weight
Artificial Intelligence,5
Renewable Energy,5
...
```

#### Keywords (scored 1-5)

```csv
Keyword,Weight
war,5
invasion,5
nuclear,5
...
```

#### Overrides

```csv
Override,Action
fox news,ban
entertainment,demote
...
```

#### Parameters

| Parameter                 | What It Does |
|---------------------------|--------------|
| `MAX_ARTICLE_HOURS`       | Maximum article age in hours in digest |
| `MAX_TOPICS`              | Maximum number of topics in digest |
| `MAX_ARTICLES_PER_TOPIC`  | Maximum number of articles per topic in digest |
| `DEMOTE_FACTOR`           | 0-1: Importance multiplier for 'demote' overrides |
| `TIMEZONE`                | Formatted user timezone, e.g. `'America/New_York'` |
| `ENABLE_GIT_PUSH`         | `true`/`false`: Automatically push updated `history.json` to GitHub |

---

## Running the Script

### Manual Run

Make sure your virtual environment is activated:

```bash
source .venv/bin/activate
python newsbot.py
```

### Automation with Cron

Edit your crontab:

```bash
crontab -e
```

Point directly to your virtual environment's Python executable (`.venv/bin/python`). This ensures all dependencies load properly without needing to activate the environment first:

```cron
# Send news digest daily at 8:00 AM
0 8 * * * /path/to/newsbot/.venv/bin/python /path/to/newsbot/newsbot.py >> /path/to/newsbot/logs/newsbot.log 2>&1

# Prune headlines older than 30 days every Friday at 5:00 PM
0 17 * * 5 /path/to/newsbot/.venv/bin/python /path/to/newsbot/prune_history.py >> /path/to/newsbot/logs/prune_history.log 2>&1
```

*(Replace `/path/to/newsbot` with the absolute path to your project directory).*

---

## Lockfile Notice

If the script fails or is force-terminated, it may leave behind a lockfile `newsbot.lock` in the project directory to prevent duplicate runs. To remove it manually:

```bash
rm newsbot.lock
```

---

## Logging

All runtime logs are saved to `logs/newsbot.log` and `logs/prune_history.log`. The `logs/` directory will be created automatically if it doesn't exist.

---

## Sample Digest

<h3>Donald Trump</h3>
<p>📰 <a href="https://www.theguardian.com/us-news/2025/may/08/trump-administration-news-updates-today">Trump news at a glance: Vance says Russia not being realistic on Ukraine, Trump says he may be right - The Guardian</a><br>
📅 Wed, 07 May 2025 10:30 PM EDT</p>

<h3>Trade War</h3>
<p>📰 <a href="https://www.newsnationnow.com/on-balance-with-leland-vittert/bolton-on-us-adversaries-under-tariffs-in-any-trade-war-everyone-suffers/">Bolton on US adversaries under tariffs: In any trade war, everyone suffers - NewsNation</a><br>
📅 Wed, 07 May 2025 10:49 PM EDT</p>

<h3>Artificial Intelligence</h3>
<p>📰 <a href="https://news.gallup.com/poll/660302/heartland-gen-zers-feel-unprepared-work.aspx">Heartland Gen Zers Feel Unprepared to Use AI at Work - Gallup News</a><br>
📅 Thu, 08 May 2025 12:20 AM EDT</p>

---
<p align="center">&copy; Copyright 2026 <a href="https://blakerayvid.com">Blake Rayvid</a>. All rights reserved.</p>