# News Digest Bot

**News Digest Bot** is a Python automation script that compiles a personalized news digest by matching **headline text** against two user-defined CSV files:

- `topics.csv` – A list of topics with importance weights.
- `keywords.csv` – A list of keywords with importance weights.

Each headline is scored based on how well it matches entries from these two files. The top results are filtered, deduplicated, and delivered in an HTML email.

---

## Features

- Fetches trending and topic-specific headlines from Google News RSS.
- Matches each headline against `topics.csv` and `keywords.csv` using NLP normalization (stemming and lemmatization).
- Applies user-defined weights (`TOPIC_WEIGHT` and `KEYWORD_WEIGHT`) to influence scoring.
- Temporarily boosts scores for trending topics based on recent headlines.
- Deduplicates semantically similar headlines using string similarity and TF-IDF.
- Sends the final digest as a structured HTML email via Gmail SMTP.
- Cron-safe: uses a lockfile to prevent concurrent runs.
- Fully configurable parameters to fine-tune scoring, relevance, and output volume.

---

## How It Works

1. **Configuration and Data Loading**
   - Loads:
     - `topics.csv` – e.g., `Artificial Intelligence,5`
     - `keywords.csv` – e.g., `nuclear,4`
     - `history.json` – to avoid repeating headlines already sent
     - Environment variables from `.env` for email delivery

2. **Headline Matching**
   - Only the article's **headline text** is analyzed.
   - Headlines are:
     - Lowercased
     - Stemmed and lemmatized
     - Compared to normalized versions of topics and keywords

3. **Scoring and Boosting**
   - Each headline receives a score based on:
     - Matches to keywords (`KEYWORD_WEIGHT`)
     - Matches to topics (`TOPIC_WEIGHT`)
     - Matches to current top headlines (`TREND_WEIGHT`)
     - Recency bonus for newer headlines
   - Headlines must meet or exceed `MIN_ARTICLE_SCORE` to be considered.

4. **Topic and Article Filtering**
   - Up to `MAX_TOPICS` are selected per run.
   - A maximum of `MAX_ARTICLES_PER_TOPIC` articles are chosen per topic after deduplication.
   - Redundant or overly similar headlines are filtered using TF-IDF cosine similarity and sequence matching.

5. **Email Generation and Delivery**
   - Composes an HTML digest grouped by topic.
   - Includes publication dates, scores, and source links.
   - Sends via Gmail using credentials from `.env`.

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

| Parameter                  | Description |
|---------------------------|-------------|
| `TREND_WEIGHT`            | Boost for topics found in top headlines (1–5) |
| `TOPIC_WEIGHT`            | Influence of topic scores from `topics.csv` (1–5) |
| `KEYWORD_WEIGHT`          | Influence of keyword matches from `keywords.csv` (1–5) |
| `DEDUPLICATION_THRESHOLD` | Threshold for similarity-based deduplication (0.0–1.0) |
| `MIN_ARTICLE_SCORE`       | Minimum score required for an article to be included |
| `MAX_TOPICS`              | Maximum number of topics to include in a digest |
| `MAX_ARTICLES_PER_TOPIC`  | Cap on number of articles per topic |
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

```
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