# News Digest Bot

This Python script fetches the latest Google News RSS headlines for a user-supplied list of topics and sends a nicely formatted email digest via Gmail. It prioritizes high-importance headlines using keyword and topic scoring, and ensures each email contains fresh, non-repeating articles. Designed to run daily using `cron` on any Unix-based system.

---

## How it works

- Finds top news stories from Google News
- Picks the ones that match your interests
- Scores and filters articles based on relevance and freshness
- Avoids showing you the same headlines twice
- Sends you a clean, organized email with the best stories

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
