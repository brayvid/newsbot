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
pip3 install nltk requests python-dotenv scikit-learn google-generativeai
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

<h3>Artificial Intelligence</h3>
<p>📰 <a href="https://malaysia.news.yahoo.com/singapore-sea-lion-ai-model-052720584.html">Singapore’s Sea-Lion AI model gains traction with firms like Indonesia’s GoTo Group, offering 13 regional languages - Yahoo</a><br>
📅 Mon, 05 May 2025 01:27 AM EDT</p>

<h3>Donald Trump</h3>
<p>📰 <a href="https://www.cnn.com/2025/05/04/politics/trump-alcatraz-prisons-reopen">Trump says he is directing Bureau of Prisons to reopen Alcatraz to house ‘ruthless and violent offenders’ - CNN</a><br>
📅 Sun, 04 May 2025 10:21 PM EDT</p>

<h3>China</h3>
<p>📰 <a href="https://www.nytimes.com/2025/05/05/opinion/china-ai-deepseek-tiktok.html">Opinion | DeepSeek. Temu. TikTok. China Tech Is Starting to Pull Ahead. - The New York Times</a><br>
📅 Mon, 05 May 2025 01:00 AM EDT</p>

<h3>Hamas</h3>
<p>📰 <a href="https://www.reuters.com/world/middle-east/hamas-executes-looters-gaza-food-crisis-worsens-under-israeli-blockade-2025-05-04/">Hamas executes looters in Gaza as food crisis worsens under Israeli blockade - Reuters</a><br>
📅 Sun, 04 May 2025 11:00 PM EDT</p>

<h3>Inflation</h3>
<p>📰 <a href="https://www.bostonglobe.com/2025/05/05/business/federal-reserve-interest-rates/">Federal Reserve likely to defy Trump, keep rates unchanged this week - The Boston Globe</a><br>
📅 Mon, 05 May 2025 12:53 AM EDT</p>

<h3>Renewable Energy</h3>
<p>📰 <a href="https://www.washingtonpost.com/world/2025/05/04/china-united-states-green-energy-gap/">Trump has cut global climate finance. China is more than happy to step in. - The Washington Post</a><br>
📅 Mon, 05 May 2025 02:00 AM EDT</p>

<h3>Ukraine</h3>
<p>📰 <a href="https://www.independent.co.uk/news/world/europe/ukraine-russia-war-drones-fighter-jet-putin-ceasefire-latest-news-b2744844.html">Ukraine-Russia war latest: Zelensky says Putin could call ceasefire ‘even today’ if he wanted to - The Independent</a><br>
📅 Mon, 05 May 2025 01:59 AM EDT</p>
<hr>