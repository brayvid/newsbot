# News Digest Bot

This script compiles an email digest of news articles matched to a user's priority topics and keywords. It fetches top headlines from Google News RSS, scores them for relevance, deduplicates similar stories, and sends the results via email.

---

## Features

- Pulls top Google News RSS headlines and topic-specific headlines
- Matches articles to user-defined topics and keywords using NLP scoring
- Automatically boosts relevance for trending stories
- Deduplicates similar articles based on semantic similarity
- Sends results in an HTML email digest
- Cron-safe with a lockfile to avoid concurrent runs
- Customizable scoring parameters and thresholds

---

## How It Works

1. **Keyword and Topic Matching**  
   Each article is normalized (stemmed and lemmatized) and scored based on keyword matches and similarity to configured topics.

2. **Trending Topics Boost**  
   Trending headlines from Google's top feed are matched to topics and temporarily boosted using `TREND_WEIGHT`.

3. **Topic Selection and Filtering**  
   The top `MAX_TOPICS` topics are chosen based on score, prioritizing trending ones. A fallback pool can fill in remaining slots.

4. **Article Selection per Topic**  
   The top-scoring articles for each topic are filtered for diversity using cosine similarity and capped at `MAX_ARTICLES_PER_TOPIC`.

5. **Email Generation**  
   An HTML digest is constructed and sent via Gmail SMTP.

---

## Directory Structure

```plaintext
digest-bot/
├── digest_bot.py         # Main script
├── requirements.txt      # Package requirements file
├── topics.csv            # Your topics and their importance scores
├── keywords.csv          # Your criticality keywords and their importance scores
├── history.json          # Tracks all previously sent articles (not committed)
├── .env                  # Email credentials (not committed)
├── logs/                 # Logs folder (not committed)
│   └── digest_bot.log    # Cron + runtime logs (not committed)
```
---

## Configuration Parameters

| Parameter                  | Description |
|---------------------------|-------------|
| `TREND_WEIGHT`            | Boost applied to topics appearing in top headlines (1-5) |
| `TOPIC_WEIGHT`            | Influence of `topics.csv` weights on article scores (1-5) |
| `KEYWORD_WEIGHT`          | Influence of `keywords.csv` matches in article titles (1-5) |
| `MIN_ARTICLE_SCORE`       | Minimum score required for an article to be included |
| `MAX_TOPICS`              | Maximum number of topics included in a digest |
| `MAX_ARTICLES_PER_TOPIC`  | Maximum number of articles per topic |
| `DEDUPLICATION_THRESHOLD` | Threshold for similarity filtering (0 to 1 scale) |

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
python3 -W ignore digest_bot.py
```

To automate daily delivery:

```bash
crontab -e
```

Add a line like the following:

```
0 8 * * * cd /path/to/news-digest-bot && /usr/bin/env python3 -W ignore digest_bot.py >> logs/digest_bot.log 2>&1
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

- You can fine-tune `TOPIC_WEIGHT`, `KEYWORD_WEIGHT`, and `TREND_WEIGHT` to prioritize certain types of articles.
- Lower `MIN_ARTICLE_SCORE` if your digests are too sparse.
- Increase `MAX_ARTICLES_PER_TOPIC` to allow more coverage per topic.
- Use richer keyword/topic CSVs for better matching.

---