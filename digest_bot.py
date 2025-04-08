# Author: Blake Rayvid <https://github.com/brayvid>

#!/usr/bin/env python3
import sys
import csv
import smtplib
import html
import logging
from datetime import datetime, timedelta
from email.message import EmailMessage
import xml.etree.ElementTree as ET
import requests
import json
import os
from collections import defaultdict
from difflib import SequenceMatcher

# ─── Tiered Keyword Scoring ─────────────────────────────────────────────
KEYWORD_WEIGHTS = {
    "war": 5, "invasion": 5, "nuclear": 5, "pandemic": 5, "emergency": 5, "cyberattack": 5,
    "explosion": 5, "outbreak": 5, "recession": 5, "indictment": 5, "resignation": 5, "bankruptcy": 5,
    "crisis": 3, "sanctions": 3, "ceasefire": 3, "layoffs": 3, "breach": 3, "scandal": 3, "fatal": 3,
    "heatwave": 3, "wildfire": 3, "earthquake": 3, "collapse": 3, "data leak": 3, "charged": 3,
    "inflation": 2, "missile": 2, "protests": 2, "subpoena": 2, "legislation": 2, "executive order": 2,
    "drought": 2, "ransomware": 2, "record profit": 2, "launch": 2, "leaked": 2,
    "clinical trial": 1, "vaccine": 1, "research study": 1, "IPO": 1, "quarterly report": 1,
    "greenhouse gases": 1, "pollution": 1, "mutation": 1, "demo": 1, "historic": 1
}

def score_text(text):
    text = text.lower()
    score = 0
    for keyword, weight in KEYWORD_WEIGHTS.items():
        if keyword in text:
            score += weight
    score += len(text.split()) // 20
    return score

def dedupe_articles(articles, threshold=0.75):
    unique = []
    for article in sorted(articles, key=lambda x: -x["score"]):
        if all(SequenceMatcher(None, article["title"].lower(), seen["title"].lower()).ratio() < threshold for seen in unique):
            unique.append(article)
    return unique

# ─── Lockfile Setup ─────────────────────────────────────────────────────
LOCKFILE = "/tmp/digest_bot.lock"

if os.path.exists(LOCKFILE):
    print("Script is already running. Exiting.")
    sys.exit()
else:
    with open(LOCKFILE, 'w') as f:
        f.write("locked")

try:
    # ─── Logging Setup ─────────────────────────────────────────────────
    BASE_DIR = os.path.dirname(__file__)
    LOG_PATH = os.path.join(BASE_DIR, "logs/digest.log")
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO)
    logging.info(f"Script started at {datetime.now()}")

    # ─── Config / Environment ──────────────────────────────────────────
    EMAIL_FROM = os.getenv("GMAIL_USER", "your@email.com")
    EMAIL_TO = os.getenv("MAILTO", EMAIL_FROM)
    SMTP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587

    TOPIC_CSV = os.path.join(BASE_DIR, "topics.csv")
    LAST_SEEN_FILE = os.path.join(BASE_DIR, "last_seen.json")

    # ─── Load Previous State ───────────────────────────────────────────
    if os.path.exists(LAST_SEEN_FILE):
        with open(LAST_SEEN_FILE, "r") as f:
            last_seen = json.load(f)
    else:
        last_seen = {}

    # ─── Read Topics ───────────────────────────────────────────────────
    with open(TOPIC_CSV, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        topics = [row[0].strip() for row in reader if row]

    # ─── Fetch Articles & Score ─────────────────────────────────────────
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    topic_articles = defaultdict(list)

    for topic in topics:
        feed_url = f"https://news.google.com/rss/search?q={requests.utils.quote(topic)}"

        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(feed_url, headers=headers, timeout=10)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            for item in root.findall("./channel/item"):
                title = item.findtext("title") or "No title"
                link = item.findtext("link")
                pubDate = item.findtext("pubDate")

                try:
                    pubDate_dt = datetime.strptime(pubDate, "%a, %d %b %Y %H:%M:%S %Z")
                except:
                    pubDate_dt = None

                if not pubDate_dt or pubDate_dt <= one_week_ago:
                    continue

                score = score_text(title)
                if score > 0:
                    topic_articles[topic].append({
                        "score": score,
                        "title": title,
                        "link": link,
                        "pubDate": pubDate
                    })

        except Exception as e:
            logging.warning(f"Error fetching topic '{topic}': {e}")
            continue

    # ─── Only keep most relevant topics ─────────────────────────────────
    topic_scores = [(topic, sum(article["score"] for article in articles)) for topic, articles in topic_articles.items()]
    top_topics = set(topic for topic, _ in sorted(topic_scores, key=lambda x: x[1], reverse=True)[:10])
    filtered_articles = {k: v for k, v in topic_articles.items() if k in top_topics}

    # ─── Send Email Digest ─────────────────────────────────────────────
    sent_articles = {}
    if filtered_articles:
        html_body = "<h2>Your News Digest</h2>"
        sections = []

        for topic, articles in filtered_articles.items():
            deduped = dedupe_articles(articles)
            if deduped:
                top_article = deduped[0]  # take only the highest-priority headline
                topic_key = topic.replace(" ", "_").lower()
                sent_articles[topic_key] = {"title": top_article["title"], "pubDate": top_article["pubDate"]}
                section_html = f"<h3>{html.escape(topic)}</h3>\n"
                section_html += f"""
                <p>
                    📰 <a href=\"{top_article['link']}\" target=\"_blank\">{html.escape(top_article['title'])}</a><br>
                    📅 {top_article['pubDate']} — Score: {top_article['score']}
                </p>
                """
                sections.append((top_article['score'], section_html))

        # Sort sections by score descending
        for _, html_section in sorted(sections, key=lambda x: -x[0]):
            html_body += html_section

        msg = EmailMessage()
        msg["Subject"] = f"🗞️ News Digest – {datetime.now().strftime('%Y-%m-%d')}"
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg.set_content("This is the plain-text version of your digest.")
        msg.add_alternative(html_body, subtype="html")

        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_FROM, SMTP_PASS)
                server.send_message(msg)
            logging.info("Digest email sent successfully.")
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
    else:
        logging.info("No high-priority articles to send.")

    # ─── Save State ────────────────────────────────────────────────────
    with open(LAST_SEEN_FILE, "w") as f:
        json.dump(sent_articles, f, indent=2)

finally:
    if os.path.exists(LOCKFILE):
        os.remove(LOCKFILE)
    logging.info(f"Lockfile released at {datetime.now()}")