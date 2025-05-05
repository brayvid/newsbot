# NewsBot

This Python script fetches the latest Google News RSS headlines for a user-supplied list of topics and sends a nicely formatted email digest. It uses Google Gemini to prioritize headlines. Designed to run daily using `cron` on any Unix-based system.

---

## How it works

- Reads [this configuration file](https://docs.google.com/spreadsheets/d/1OjpsQEnrNwcXEWYuPskGRA5Jf-U8e_x0x3j2CKJualg/edit?usp=sharing) on Google Sheets with topics, keywords and overrides
- Retrieves the latest news headlines for all topics from Google News RSS
- Queries Gemini to prioritize these headlines according to your preferences
- Sends you a clean HTML email digest
- Schedule with `cron`

---

## Directory Structure

```plaintext
newsbot/
├── newsbot.py            # Main script
├── requirements.txt      # Package requirements
├── history.json          # Tracks previously sent headlines (excluded from version control)
├── .env                  # Email credentials and configuration (excluded from version control)
├── logs/                 # Logging directory (excluded from version control)
│   └── newsbot.log       # Runtime logs and cron output
```

---

## Configuration Parameters

| Parameter                  | What It Does |
|---------------------------|--------------|
| `MAX_ARTICLE_AGE`         | Maximum article age in hours in digest |
| `MAX_TOPICS`              | Maximum number of topics in digest |
| `MAX_ARTICLES_PER_TOPIC`  | Maximum number of articles per topic in digest |
| `DEMOTE_FACTOR`           | 0-1: Importance multiplier for 'demote' overrides |

---

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/brayvid/newsbot.git
cd newsbot
```

### 2. Install Dependencies

```bash
pip3 install -r requirements.txt
```

Or manually:

```bash
pip3 install nltk requests python-dotenv google-generativeai
```


### 3. Prepare Environment File

`nano .env` – contains email credentials, recipient(s), and Gemini API key:

```env
GMAIL_USER=your_email@gmail.com
GMAIL_APP_PASSWORD=your_app_password
MAILTO=recipient1@example.com,...
GEMINI_API_KEY=your_gemini_api_key
```

(You must [enable 2FA](https://myaccount.google.com/security) and [generate an App Password](https://support.google.com/accounts/answer/185833) for your Gmail account.)


---

## Running the Script

```bash
python3 newsbot.py
```

To automate daily delivery:

```bash
crontab -e
```

Add a line like the following:

```cron
0 8 * * * cd /path/to/newsbot && /usr/bin/env python3 newsbot.py >> /path/to/newsbot/logs/newsbot.log 2>&1
```

This runs the script every day at 8:00 AM server time.

---

## Lockfile Notice

If the script fails or is force-terminated, it may leave behind a lockfile `newsbot.lock` in the project directory. To remove it manually:

```bash
rm newsbot.lock
```

---

## Logging

All script logs are saved to `logs/newsbot.log`. The `logs/` directory will be created automatically if it doesn't exist.

---
<br>

## Sample Digest

<h3>Donald Trump</h3>
<p>📰 <a href="https://www.bbc.com/news/articles/cze17n02gego">Trump orders reopening of notorious Alcatraz prison - BBC</a><br>
📅 Mon, 05 May 2025 04:03 AM EDT</p>

<h3>Trade War</h3>
<p>📰 <a href="https://www.reuters.com/business/finance/strategists-optimistic-china-even-us-china-trade-war-climbdown-looks-far-off-2025-05-05/">Strategists optimistic on China even as US-China trade war climbdown looks far off - Reuters</a><br>
📅 Mon, 05 May 2025 05:22 AM EDT</p>

<h3>Financial Markets</h3>
<p>📰 <a href="https://www.bloomberg.com/news/articles/2025-05-04/oil-slumps-after-opec-agrees-another-supply-surge-markets-wrap">Asian Currencies Jump on Weaker Dollar, Oil Falls: Markets Wrap - Bloomberg.com</a><br>
📅 Mon, 05 May 2025 03:24 AM EDT</p>

<h3>Inflation</h3>
<p>📰 <a href="https://www.bloomberg.com/news/articles/2025-05-05/swiss-inflation-drops-to-zero-as-snb-mulls-more-rate-cuts">Swiss Inflation Drops to Zero as SNB Mulls More Interest Rate Cuts - Bloomberg.com</a><br>
📅 Mon, 05 May 2025 02:30 AM EDT</p>

<h3>Russia</h3>
<p>📰 <a href="https://www.aljazeera.com/news/2025/5/5/russia-reports-ukrainian-drone-attack-on-moscow-before-may-9-events">Russia reports Ukrainian drone attack on Moscow ahead of May 9 events - Al Jazeera</a><br>
📅 Mon, 05 May 2025 05:56 AM EDT</p>

<h3>Renewable Energy</h3>
<p>📰 <a href="https://www.yahoo.com/news/spains-blackout-highlights-renewables-grid-095751267.html">Spain's blackout highlights renewables' grid challenge - Yahoo</a><br>
📅 Mon, 05 May 2025 05:57 AM EDT</p>

<hr>