# News Digest Bot

This Python script fetches the latest Google News RSS headlines for a curated list of topics and sends a nicely formatted email digest via Gmail. It uses both a keyword scoring system and your topic preferences from a CSV file, and intelligently boosts relevance using current trending topics from a free news API. It ensures each email contains timely, non-repeating, high-priority articles. Designed to run daily using `cron` on any Unix-based system.


## 📁 Directory Structure

```plaintext
digest-bot/
├── digest_bot.py         # Main script
├── requirements.txt      # Requirements file
├── scored_topics.csv     # Your topics and their importance scores
├── last_seen.json        # Tracks all previously sent articles (not committed)
├── .env                  # Email + API credentials (not committed)
├── logs/                 # Logs folder (not committed)
│   └── digest_bot.log    # Cron + runtime logs
```
---

## 🛠️ Configuration Parameters

The script uses several configurable parameters:

| Parameter              | Description                                                                      |
|------------------------|----------------------------------------------------------------------------------|
| `TRENDING_WEIGHT`      | Boost added to a topic’s score if it’s found in trending news (eg. `1–5`)        |
| `TOPIC_WEIGHT`         | Weight multiplier for topic scores from `scored_topics.csv` (eg. `1–5`)          |
| `KEYWORD_WEIGHT`       | Weight multiplier for keyword scores (eg. `1–5`)                                 |
| `MIN_ARTICLE_SCORE`    | Minimum combined score required to include a headline (default: `20`)            |
| `MAX_TOPICS`           | Max number of top topics to include in the digest (default: `10`)                |
| `USE_TRENDING_TOPICS`  | Enable/disable boosting topics that match trending headlines (`True` or `False`) |

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

- **Trending awareness**: Relevance is boosted for topics matching today’s trending headlines (via `newsdata.io`).
- **Topic importance scoring** from `scored_topics.csv`.
- **Headline relevance scoring** using tiered keywords.
- **Customizable scoring parameters**: Easily adjust `TRENDING_WEIGHT`, `TOPIC_WEIGHT`, `KEYWORD_WEIGHT`, `MIN_ARTICLE_SCORE` and `MAX_TOPICS` via constants.
- **Stemming + lemmatization** for smarter keyword matching.
- **Only includes articles with high combined scores (≥ 20).**
- **No repetition**: Remembers previously sent articles.
- **Nicely formatted HTML email** with clickable links.
- **Lockfile** ensures no duplicate cron runs.
- **`.env` support** for Gmail and API credentials.

---

## 🗞️ Example Digest

### Russian Invasion of Ukraine
**📰 [Ukraine War, Day 1,140: 2 Chinese Soldiers Captured While Fighting For Russia’s Invasion - EA WorldView](https://eaworldview.com/2025/04/ukraine-war-2-chinese-soldiers-captured-while-fighting-for-russias-invasion/)**

📅 *Wed, 09 Apr 2025 02:03 AM EDT* — **Score: 50**

### Inflation
**📰 [Global Investment Banks Warn of US Recession Likelihood and Inflation Pressures - kaohoon international](https://www.kaohooninternational.com/economics/555839)**

📅 *Tue, 08 Apr 2025 11:47 PM EDT* — **Score: 48**

### Cybersecurity
**📰 [AI agents emerge as potential targets for cyberattackers - CIO Dive](https://www.ciodive.com/news/ai-agents-cybersecurity-risks/744803/)**

📅 *Tue, 08 Apr 2025 04:49 PM EDT* — **Score: 45**

### Fusion Power
**📰 [Germany is making the biggest “power play” in its energy history, investing $385 million in laser-driven inertial confinement nuclear fusion. - Farmingdale Observer](https://farmingdale-observer.com/2025/04/08/germany-is-making-the-biggest-power-play-in-its-energy-history-investing-385-million-in-laser-driven-inertial-confinement-nuclear-fusion/)**

📅 *Tue, 08 Apr 2025 09:26 PM EDT* — **Score: 40**

### Israel-Hamas War
**📰 [Israeli, Palestinian students protest Gaza war at Hebrew University of Jerusalem: ‘Stop the War’ - New York Post](https://nypost.com/2025/04/08/world-news/israeli-palestinian-students-protest-gaza-war-at-jerusalem-university/)**
  
📅 *Tue, 08 Apr 2025 04:05 PM EDT* — **Score: 40**

### North Korea
**📰 [North Korean Leader's Sister Fires Nuclear Warning at Trump - Newsweek](https://www.newsweek.com/north-korea-kim-jong-un-sister-nuclear-weapons-warning-us-donald-trump-2057234)**

📅 *Wed, 09 Apr 2025 02:53 AM EDT* — **Score: 40**

### Donald Trump
**📰 [Trump Tariffs Live Updates: 'Have abundant means to fight trade war,' says China as Trump tariffs come into effect - Times of India](https://timesofindia.indiatimes.com/world/us/donald-trump-tariffs-live-updates-reciprocal-tariffs-us-stock-market-china-canada-india-uk-united-states/liveblog/120104222.cms)**

📅 *Wed, 09 Apr 2025 03:39 AM EDT* — **Score: 32**

### Intelligence Agencies
**📰 [Can you believe this? North Korean hackers pose as U.S developers in Fortune 500 firms, funnel millions to Kim Jong Un's nuclear weapons programs - MSN](https://www.msn.com/en-in/money/news/can-you-believe-this-north-korean-hackers-pose-as-u-s-developers-in-fortune-500-firms-funnel-millions-to-kim-jong-un-s-nuclear-weapons-programs/ar-AA1CxnG2?ocid=finance-verthp-feeds)**

📅 *Tue, 08 Apr 2025 10:17 PM EDT* — **Score: 30**

### Vladimir Putin
**📰 [Russia says the future of nuclear arms control with US and others looks bleak for now - Reuters](https://www.reuters.com/world/kremlin-says-it-is-hard-imagine-talks-with-us-new-nuclear-arms-reduction-treaty-2025-04-08/)**

📅 *Tue, 08 Apr 2025 06:45 AM EDT* — **Score: 28**

### Public Health
**📰 [Six people honored with 2025 GFPH Public Health Champion awards - Grand Forks Herald](https://www.grandforksherald.com/news/local/six-people-honored-with-2025-gfph-public-health-champion-awards)**

📅 *Tue, 08 Apr 2025 11:05 PM EDT* — **Score: 25**

---