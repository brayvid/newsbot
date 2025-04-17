# News Digest Bot

This Python script fetches the latest Google News RSS headlines for a user-supplied list of topics and sends a nicely formatted email digest via Gmail. It prioritizes high-importance headlines using keyword and topic scoring, and ensures each email contains fresh, non-repeating articles. Designed to run daily using `cron` on any Unix-based system.

---

## How it works

- Finds top news stories from Google News
- Selects topics in `topics.csv` that have similarity to top headlines
- Scores and filters the latest stories for those topics
- Avoids showing you the same headlines twice
- Sends you a clean HTML email digest
- Schedule with `cron`

---

## Directory Structure

```plaintext
news-digest-bot/
├── digest_bot.py         # Main script and parameters
├── requirements.txt      # Package requirements
├── topics.csv            # List of topics and weights
├── keywords.csv          # List of keywords and weights
├── history.json          # Tracks previously sent headlines (excluded from version control)
├── .env                  # Email credentials and configuration (excluded from version control)
├── logs/                 # Logging directory (excluded from version control)
│   └── digest_bot.log    # Runtime logs and cron output
```

---

## Configuration Parameters

| Parameter                  | What It Does |
|---------------------------|--------------|
| `TREND_WEIGHT`            | 1-5: Boost for trending topics |
| `TOPIC_WEIGHT`            | 1-5: Boost for topics in `topics.csv` |
| `KEYWORD_WEIGHT`          | 1-5: Boost for matching keywords |
| `TREND_OVERLAP_THRESHOLD` | 0-1: Token overlap % needed to detect a trending topic |
| `DEDUPLICATION_THRESHOLD` | 0-1: Similarity level to remove near-duplicate headlines |
| `MIN_ARTICLE_SCORE`       | Articles below this score are ignored |
| `MAX_TOPICS`              | Number of topics per digest |
| `MAX_ARTICLES_PER_TOPIC`  | Number of articles per topic |

---

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/brayvid/news-digest-bot.git
cd news-digest-bot
```

### 2. Install Dependencies

```bash
pip3 install -r requirements.txt
```

Or manually:

```bash
pip3 install nltk requests python-dotenv scikit-learn
```


### 3. Prepare Configuration Files

- `.env` – contains email credentials and recipient:

  ```env
  GMAIL_USER=your_email@gmail.com
  GMAIL_APP_PASSWORD=your_app_password
  MAILTO=recipient@example.com
  ```
  
- `topics.csv` – your list of prioritized topics, one per line:

  ```
  Topic,Weight
  Artificial Intelligence,5
  Renewable Energy,5
  ...
  ```
- `keywords.csv` – relevant keywords to influence scoring:

  ```
  Keyword,Weight
  war,5
  invasion,5
  nuclear,5
  ...
  ```

---

## Running the Script

```bash
python3 digest_bot.py
```

To automate daily delivery:

```bash
crontab -e
```

Add a line like the following:

```cron
0 8 * * * cd /path/to/news-digest-bot && /usr/bin/env python3 digest_bot.py >> logs/digest_bot.log 2>&1
```

This runs the script every day at 8:00 AM server time.

---

### Lockfile Notice

If the script fails or is force-terminated, it may leave behind a lockfile at `/tmp/digest_bot.lock`. To remove it manually:

```bash
rm /tmp/digest_bot.lock
```

---

## Logging

All script logs are saved to `logs/digest_bot.log`. The `logs/` directory will be created automatically if it doesn't exist.

---

## Customization Tips

- Adjust `TREND_WEIGHT`, `TOPIC_WEIGHT`, and `KEYWORD_WEIGHT` to fine-tune relevance scoring.
- Lower `MIN_ARTICLE_SCORE` to include more articles.
- Use richer keyword and topic lists for more comprehensive coverage.
- Increase `MAX_ARTICLES_PER_TOPIC` if you want more results per topic.

---
<br>

# Sample Digest

  <h2>The Pentagon</h2>
  <p>📰 <a href="#">Third Pentagon appointee placed on administrative leave - CNN</a><br>
  📅 Wed, 16 Apr 2025 03:01 PM EDT — <strong>Score: 65</strong></p>

  <h2>Research and Development</h2>
  <p>📰 <a href="#">OpenAI releases o3, a model that tops 99% of human competitors on IOI 2024 and Codeforces benchmarks - R&D World</a><br>
  📅 Wed, 16 Apr 2025 06:04 PM EDT — <strong>Score: 65</strong></p>

  <h2>Donald Trump</h2>
  <p>📰 <a href="#">America’s Mad King - The Atlantic</a><br>
  📅 Thu, 17 Apr 2025 10:08 AM EDT — <strong>Score: 45</strong></p>

  <h2>Public Health</h2>
  <p>📰 <a href="#">Public health sounds alarm on measles - Ouray News</a><br>
  📅 Wed, 16 Apr 2025 11:46 PM EDT — <strong>Score: 25</strong></p>

  <h2>Health Care</h2>
  <p>📰 <a href="#">Health care AI stuck in the waiting room - Politico</a><br>
  📅 Thu, 17 Apr 2025 02:00 PM EDT — <strong>Score: 20</strong></p>

  <hr>