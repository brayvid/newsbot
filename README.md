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
├── newsbot.py            # Main script
├── requirements.txt      # Package requirements
├── history.json          # Tracks previously sent headlines
├── .env                  # Email credentials and configuration (excluded from version control)
├── logs/                 # Logging directory (excluded from version control)
│   └── newsbot.log       # Runtime logs and cron output
```


## Setup

### 1. Clone the repository

```bash
git clone https://github.com/brayvid/newsbot.git
cd newsbot
```

### 2. Install dependencies

```bash
pip3 install -r requirements.txt
```

Or manually:

```bash
pip3 install nltk requests python-dotenv google-generativeai
```


### 3. Prepare environment file

`nano .env` – contains email credentials, recipient(s), and Gemini API key:

```env
GMAIL_USER=your_email@gmail.com
GMAIL_APP_PASSWORD=your_app_password
MAILTO=recipient1@example.com,...
GEMINI_API_KEY=your_gemini_api_key
```

(You must [enable 2FA](https://myaccount.google.com/security) and [generate an App Password](https://support.google.com/accounts/answer/185833) for your Gmail account, and [generate a Gemini API Key](https://ai.google.dev/gemini-api/docs/api-key).)



### 4. Specify preferences

  
#### Topics (scored 1-5)


  ```
  Topic,Weight
  Artificial Intelligence,5
  Renewable Energy,5
  ...
  ```
#### Keywords (scored 1-5)


  ```
  Keyword,Weight
  war,5
  invasion,5
  nuclear,5
  ...
  ```

#### Overrides


  ```
  Override,Action
  fox news,ban
  entertainment,demote
  ...
  ```

#### Options

| Parameter                 | What It Does |
|---------------------------|--------------|
| `MAX_ARTICLE_HOURS`       | Maximum article age in hours in digest |
| `MAX_TOPICS`              | Maximum number of topics in digest |
| `MAX_ARTICLES_PER_TOPIC`  | Maximum number of articles per topic in digest |
| `DEMOTE_FACTOR`           | 0-1: Importance multiplier for 'demote' overrides |
| `TIMEZONE`                | Formatted user timezone, eg. 'America/New_York' |

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
<p>📰 <a href="https://www.theguardian.com/us-news/2025/may/08/trump-administration-news-updates-today">Trump news at a glance: Vance says Russia not being realistic on Ukraine, Trump says he may be right - The Guardian</a><br>
📅 Wed, 07 May 2025 10:30 PM EDT</p>

<h3>Trade War</h3>
<p>📰 <a href="https://www.newsnationnow.com/on-balance-with-leland-vittert/bolton-on-us-adversaries-under-tariffs-in-any-trade-war-everyone-suffers/">Bolton on US adversaries under tariffs: In any trade war, everyone suffers - NewsNation</a><br>
📅 Wed, 07 May 2025 10:49 PM EDT</p>

<h3>Artificial Intelligence</h3>
<p>📰 <a href="https://news.gallup.com/poll/660302/heartland-gen-zers-feel-unprepared-work.aspx">Heartland Gen Zers Feel Unprepared to Use AI at Work - Gallup News</a><br>
📅 Thu, 08 May 2025 12:20 AM EDT</p>

<h3>China</h3>
<p>📰 <a href="https://www.reuters.com/markets/commodities/chinas-byd-tsingshan-scrap-plans-chile-lithium-plants-newspaper-reports-2025-05-07/">China's BYD, Tsingshan scrap plans for Chile lithium plants - Reuters</a><br>
📅 Wed, 07 May 2025 07:53 PM EDT</p>

<h3>Recession</h3>
<p>📰 <a href="https://kfgo.com/2025/05/07/pimco-sees-heightened-us-recession-risks-ft-reports/">PIMCO sees heightened US recession risks, FT reports - The Mighty 790 KFGO</a><br>
📅 Thu, 08 May 2025 01:20 AM EDT</p>

<h3>Republican Party</h3>
<p>📰 <a href="https://katv.com/news/local/judge-dismisses-republican-party-of-arkansas-civil-rights-lawsuit-governor-sarah-huckabee-sanders-secretary-of-state-john-thurston-cole-jester-rpa-federal-brian-miller-rogers-little-rock">Judge dismisses Republican Party of Arkansas civil rights lawsuit - KATV</a><br>
📅 Wed, 07 May 2025 08:55 PM EDT</p>

<hr>

<small>Gemini recommends these articles among 759 published in the last 6 hours based on your <a href="https://docs.google.com/spreadsheets/d/1OjpsQEnrNwcXEWYuPskGRA5Jf-U8e_x0x3j2CKJualg/edit?usp=sharing">preferences</a>.</small>