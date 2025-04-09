# News Digest Bot

This Python script fetches the latest Google News RSS headlines for a curated list of topics and sends a nicely formatted email digest via Gmail. It uses both a keyword scoring system and topic importance from a CSV file, and intelligently boosts relevance using trending topics from a free news API. It ensures each email contains timely, non-repeating, high-priority articles. Designed to run daily using `cron` on any Unix-based system.

---

## 📁 Directory Structure

```plaintext
digest-bot/
├── digest_bot.py         # Main script
├── requirements.txt      # Requirements file
├── scored_topics.csv     # Your topics and their importance scores
├── last_seen.json        # Tracks all previously sent articles (not committed)
├── .env                  # Email + API credentials (not committed)
├── logs/                 # Logs folder (not committed)
│   └── digest_bot.log    # Cron + runtime logs (not committed)
```

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

- **Trending awareness**: Relevance is boosted for topics matching today’s trending headlines (via `newsdata.io`)
- **Topic importance scoring** from `scored_topics.csv`
- **Headline relevance scoring** using tiered keywords
- **Stemming + lemmatization** for smarter keyword matching
- **Only includes articles with high combined scores (≥ 20)**
- **No repetition**: Remembers previously sent articles
- **Nicely formatted HTML email** with clickable links
- **Lockfile** ensures no duplicate cron runs
- **`.env` support** for Gmail and API credentials

---

## 🗞️ Example Digest

### Inflation
- **📰 [Trade War Boosts Inflation Expectations, Bank of Canada Says - Yahoo Finance](https://finance.yahoo.com/news/trade-war-boosts-inflation-expectations-150948435.html)**  
  📅 *Mon, 07 Apr 2025 11:09 AM EDT* — **Score: 40**

### Israel-Hamas War
- **📰 [Hamas ready to free all hostages at once for end to war — Palestinian official - The Times of Israel](https://www.timesofisrael.com/hamas-ready-to-free-all-hostages-at-once-for-end-to-war-palestinian-official/)**  
  📅 *Wed, 02 Apr 2025 07:20 PM EDT* — **Score: 30**

### Russian Invasion of Ukraine
- **📰 ['Putin intends to do anything but end war': Zelenskyy claims Ukraine captured two Chinese nationals fight - Times of India](https://timesofindia.indiatimes.com/world/europe/putin-intends-to-do-anything-but-end-war-zelenskyy-claims-ukraine-captured-two-chinese-nationals-fighting-for-russia/articleshow/120097414.cms)**  
  📅 *Tue, 08 Apr 2025 09:23 AM EDT* — **Score: 30**

### War
- **📰 ['Economic nuclear war': Some billionaires criticize Trump's tariffs - ABC News](https://abcnews.go.com/Business/economic-nuclear-war-billionaires-criticize-trumps-tariffs/story?id=120570107)**  
  📅 *Mon, 07 Apr 2025 03:07 PM EDT* — **Score: 30**

### Donald Trump
- **📰 [Tracking Trump’s Tariffs and the Global Trade War - The New York Times](https://www.nytimes.com/article/trump-tariffs-canada-mexico-china.html)**  
  📅 *Wed, 09 Apr 2025 12:41 AM EDT* — **Score: 28**

### Cybersecurity
- **📰 [OCC falls victim to major cybersecurity breach - American Banker](https://www.americanbanker.com/news/occ-was-hit-by-major-cybersecurity-breach)**  
  📅 *Tue, 08 Apr 2025 03:07 PM EDT* — **Score: 25**

### Fusion Power
- **📰 [Startup Says Its Nuclear Fusion Rocket Could Cut Time to Mars in Half - Futurism](https://futurism.com/nuclear-fusion-rocket-cut-time-mars-half)**  
  📅 *Sun, 06 Apr 2025 11:15 AM EDT* — **Score: 25**

### Public Health
- **📰 [April declared Parkinson’s Awareness Month by Laredo Public Health Department - KGNS](https://www.kgns.tv/2025/04/08/april-declared-parkinsons-awareness-month-by-laredo-public-health-department/)**  
  📅 *Tue, 08 Apr 2025 04:27 PM EDT* — **Score: 25**

### North Korea
- **📰 [(News Focus) 6 months into troop deployment to Russia, N. Korea rewarded with key military tech, economic aid - Yonhap News Agency](https://en.yna.co.kr/view/AEN20250409005500315)**  
  📅 *Wed, 09 Apr 2025 12:33 AM EDT* — **Score: 24**

### Vladimir Putin
- **📰 [Citing war in Ukraine, dozens of groups call on NHL to reject hockey matchups with Russian league - NBC News](https://www.nbcnews.com/sports/nhl/citing-war-ukraine-dozens-groups-call-nhl-reject-hockey-matchups-russi-rcna200121)**  
  📅 *Mon, 07 Apr 2025 06:21 PM EDT* — **Score: 24**

---