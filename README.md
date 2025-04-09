# News Digest Bot

This Python script fetches the latest Google News RSS headlines for a curated list of topics and sends a nicely formatted email digest via Gmail. It uses both a keyword scoring system and topic criticality from a CSV file, and intelligently boosts relevance using **trending topics** from a free news API. It ensures each email contains timely, non-repeating, high-priority articles. Designed to run daily using `cron` on any Unix-based system.

---

## 📁 Directory Structure

```plaintext
digest-bot/
├── digest_bot.py         # Main script
├── scored_topics.csv     # Topics and their criticality scores
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

## 🗞️ Sample Digest

### Inflation
- **📰 [Trade War Boosts Inflation Expectations, Bank of Canada Says - Yahoo Finance](https://news.google.com/rss/articles/CBMijgFBVV95cUxNZTdITF9QUW1LX2JJLXJVcjR0aGJKZjJVaWF6dndiMlpfcFdDYlNnWldmRTR5SDhlTnZFWHFmWmU2VFhJUUtmU19mOTR1dUVlZWhnT2RBYzVreHBiYnd2MDF4eU1BX2lmc1JNYm9vNl9kbGFNdzlUS3pIdWUwRjljWUs5Q0VDdXhvcS1qbGlR?oc=5)**  
  📅 *Mon, 07 Apr 2025 11:09 AM EDT* — **Score: 40**

### Israel-Hamas War
- **📰 [Hamas ready to free all hostages at once for end to war — Palestinian official - The Times of Israel](https://news.google.com/rss/articles/CBMiqwFBVV95cUxPV3dCengzRExiVmJFTlI0SWZPZXk2aC1JVWRlODNMMDFpeHJsOXM0Y2JDbEM3VTgwNXJvY1Rvd3Qwci14WEZUdHg4aTU5d19LUkxSOEhWcmJmZEZzdEd5V0t3MHUzZ25NWTVRZzBJR1g4Zk1SeTZ0TUZpODFHNFFoVUZlaGFRazhmVGt1QTZUUUhtQUs4bUZ2U2QyeTJkbmF4QVNkMGFuZ3kzUU3SAbABQVVfeXFMUDdPcnZnaERGLU9KMFBXNzZPWGdUalJfenI3a2gwZ0ZuUXVDdm5jQVQ0QnN0RVpHNUdLSnVaQ3BKV3EwQ0cxWEJsTDhKZHRYeVNEdGtVam10Yk94SUI4OUNEXzJaRkwzdkx4RmZuRUhQNFlyLVNYOXc3dGdCX0FRY1FuMkd0R3BtN1lIbW5FZVlGby1sMXR3Q1lUSzhpd2pTYWRWMDVvZGF4Smh6azdiSXk?oc=5)**  
  📅 *Wed, 02 Apr 2025 07:20 PM EDT* — **Score: 30**

### Russian Invasion of Ukraine
- **📰 ['Putin intends to do anything but end war': Zelenskyy claims Ukraine captured two Chinese nationals fight - Times of India](https://news.google.com/rss/articles/CBMimwJBVV95cUxOSl9tdjhPQkFQUHV1dnc4cElENzRDc2YyYjBidzNHMzJ3MGJfZ0FWUUdOQ1hDN0lVOTJ5YllDT0pveE9QS1daQWNPakw2RThjd1Fjdl8tMW9WcVJpZV81bmo1SFc2X2VWOVJSeVR5Qm40UUVDSERycVpGN0lhc1h1T05wX3AtWk5USE9jeXJ2RlBldkVwX0s1UkRsb3Rib2MweWR0VDBYTjdIYmwtNTA4ZV9KU1hLZjFIcWR4QV9pOWIyeDBYQTgtUkVYeE5jZ2VPOFFYRXJVNFJKV2pyUWljcnJTcHBvQlBtZXhLb3ltZlpSWDFHNTN3eDYwb095c2dvSWJnVWI3ZVYyM1lOcWM1cFppN3VPUTNVVVFz0gGgAkFVX3lxTE9EZGJGZEEzdi1iUjE0QjJRa1VmUEVtTU9CSTBqTmtvLUdnd29lNDY0cWZyeDJXSzVsLWNVY1ZXTWRQQVdZVEJWUTJRQWxDNXFXWndfdGxXYlVTYm9NZDI1R0lXSEFxTHE2b1F6TVJCU1NOb2ZRVnJDUDJjX1p5bHNvUHZGU18tcG84VFBRLVgxdV9odWpDdC1VQW5LQ1RJSm5ScVQ2NnFmQ240UFV6U214T2xkc0lDbkU2Q3hEX2hqaVRmMV9TN3M3ZUg5YVUya0NhRW1xNGJIdXRJaHhERFNIQ3J4VHpLekJlUC1BRUpKZzA1dEFDaHBWbU5yNUNUMjVOaGFURXVIRkJ1QVI2YXBpaXN2bkZFUkJFRmdqTjNLTg?oc=5)**  
  📅 *Tue, 08 Apr 2025 09:23 AM EDT* — **Score: 30**

### War
- **📰 ['Economic nuclear war': Some billionaires criticize Trump's tariffs - ABC News](https://news.google.com/rss/articles/CBMirgFBVV95cUxOSzVFcUZSX2kwNTd6WFNZT2Naekp6bllVT0dhX2ktNkxRNERSTlZyUENjYkMzN1FrTzJXRlpSeDJ0aHRaNVpfMlpJRnFiWU5HOEl3QWQ5elIyUFcyckdDZk1rMHZUeXozdmtSdXBPYnNYTnQ3N0FuLWxUaGxDS1dxLWJDY0dhSkYzdXRVdThwekRRTWVibTMtUlBaeWhxR19iYjBuZ2V3T0NzeEFYSVHSAbMBQVVfeXFMUDdmNWJPRDVIM3F4ekdtSmplbEd2UkVfckNta0hxLVZadXEzYi1qOGdDcERUTk1ZNFJJWm9ySlFUR01ZZWYxRFdRVVFRN1piZXVsWU1jQzJsTVFGUDJtR1EwbkFZWFdUN1REOWJsRk9WOVVXcE00a3F4ZW51QXR4cGJ3SW1LZDd6c0UxcmFzd01Ob04xTEIzZGRmVVVQdGdrZ3BFMlpoZTJXdG9kNXhYakk1YjA?oc=5)**  
  📅 *Mon, 07 Apr 2025 03:07 PM EDT* — **Score: 30**

### Donald Trump
- **📰 [Tracking Trump’s Tariffs and the Global Trade War - The New York Times](https://news.google.com/rss/articles/CBMiekFVX3lxTE5uZ3NFNlhfaE9aNVZZeHRZRTFSTGNhMXp5TFBJUjRYaXpaR1F0TEJtVkROaTJ1VV8yM3p6UWZIaVowaEZWWDdZSy1xM3JPQTJlbllYajlsVXVLQW1ZdnBqRUZNOXpuS3kwQkR6dXpUdXdQLUFybWpGakhB?oc=5)**  
  📅 *Wed, 09 Apr 2025 12:41 AM EDT* — **Score: 28**

### Cybersecurity
- **📰 [OCC falls victim to major cybersecurity breach - American Banker](https://news.google.com/rss/articles/CBMigwFBVV95cUxPSGZRM2Y3dnQ2U01vTjRNVkVpYk1lcG9mR05icGR3SDFzQy1jWDM0ZDR0UU5yV1ZfbG9FLXRZVlFPdHM4RExBWThFYm9OZWhoQ01PbkpuMEhtV2Z5b0F3dE95eGVIWkpZdVdTSG9xOVdVNVNMM3Q4M1NpMHhjems4NkhIUQ?oc=5)**  
  📅 *Tue, 08 Apr 2025 03:07 PM EDT* — **Score: 25**

### Fusion Power
- **📰 [Startup Says Its Nuclear Fusion Rocket Could Cut Time to Mars in Half - Futurism](https://news.google.com/rss/articles/CBMibkFVX3lxTE5VWktLaVNFbXlkMWs5ZkxFR0szZ1JlcmFPWm1JRGNhcDZkeGp4VHVEY2lIMm05UmxfN3BQN0FUM2dldzZGOGhNOFRSMS1BNE5GRHUtTFJ0OTdDb1phZ2lSVDdQM1FSNWVtcTNQWTh3?oc=5)**  
  📅 *Sun, 06 Apr 2025 11:15 AM EDT* — **Score: 25**

### Public Health
- **📰 [April declared Parkinson’s Awareness Month by Laredo Public Health Department - KGNS](https://news.google.com/rss/articles/CBMirAFBVV95cUxPNGFPMW5KYmVMTnhIclpUSkt2ODZvMGhXVDFBRXdfdFllWkFfTUdXN1k1T0JDYUlabmx5dmV0TDN1UUFTSUExbkctNXBEQ1FnWVB3TGVFWG9PVzBEdV9KbTJtQ1JNazFacUJPQTE0bWlDVGg3THk2ektvOVpqMHUwUk9aOGotVndWNVgtdEVrc29NZDhlU3FSYVdnY0ZfTFV4X0tDc3ZaVTY4SEg30gHAAUFVX3lxTFBxVXlBbmFQWXdwX1V6VUI3X0VidTVzZTRRNm5EV3doNGtuZWFZQUo2Ym9UNDFJcE5rYTk5cFhBSV82aE1FcDNXVzZOQlpXY0dfVWtMRlZ5dnZzbGZFYW0wZVJ2LUxPYUxnaUFDenkyQncwSkJUQ3VnbnRnMUxOU0tKaVR6enJ0bEhVenQ3N25aTXhNbjdlLWkwZWkwQ0xucjcxeVdPQzlFdkFzUndZWmh6SDZIcmotUFpqY2dUWjh6LQ?oc=5)**  
  📅 *Tue, 08 Apr 2025 04:27 PM EDT* — **Score: 25**

### North Korea
- **📰 [(News Focus) 6 months into troop deployment to Russia, N. Korea rewarded with key military tech, economic aid - Yonhap News Agency](https://news.google.com/rss/articles/CBMiWkFVX3lxTE52UFRWdERjemxfeW5COUpjX3Y3QVBNWWtyZFVHQ3NobmRqSFIwZ2lPOVU1ZjdqN1Z6X2xZcEpsZm9ndGY4cDdkeWRqWXVTakZZR3ZYMmtRVWJiQQ?oc=5)**  
  📅 *Wed, 09 Apr 2025 12:33 AM EDT* — **Score: 24**

### Vladimir Putin
- **📰 [Citing war in Ukraine, dozens of groups call on NHL to reject hockey matchups with Russian league - NBC News](https://news.google.com/rss/articles/CBMitwFBVV95cUxPNDdWUkN5RktMTFhNOFg1UHhMZE5pN2RjajE2b0N6SFFiNkNpeFE4bEJiSVJ4UzVtYW5kY21wc2pTdl80ZE52Q3hPUmFiMkpmTFBiVlNiOWtOaDhmYlhqUWd2SUZKUzNqU3VWeXZtXzFILXVXYWV5NklKU1pZeHF2OVJrWmF2cDNkUGZBWXVLWEJXYlVyU2NPcXNyM3VrTWdrb2dUeGExM0Fjei10anBsdk9ZMnhDZXfSAVZBVV95cUxOTmFTQWpsSFpYVGktMnNKODlTSXEza2RUbUlTX3ZETFNsZnVIYnJvNWtaNHpWbXlhY05SY2hQSlVJT0daLVR3S1lERzMzdEZkTXdpSlRVdw?oc=5)**  
  📅 *Mon, 07 Apr 2025 06:21 PM EDT* — **Score: 24**

---