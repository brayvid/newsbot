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
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from nltk.stem import PorterStemmer, WordNetLemmatizer
import nltk
nltk.download('wordnet')
nltk.download('omw-1.4')
stemmer = PorterStemmer()
lemmatizer = WordNetLemmatizer()
from dotenv import load_dotenv
load_dotenv()

# ─── Tiered Keyword Scoring ─────────────────────────────────────────────
KEYWORD_WEIGHTS = {
    # Score 5 (Highest Relevance) - 5 keywords
    "war": 5, "invasion": 5, "nuclear": 5, "pandemic": 5, "emergency": 5, 

    # Score 4 - 10 keywords (twice as many as Score 5)
    "cyberattack": 4, "explosion": 4, "outbreak": 4, "recession": 4, "indictment": 4,
    "resignation": 4, "bankruptcy": 4, "famine": 4, "flooding": 4, "terrorism": 4,

    # Score 3 - 20 keywords (twice as many as Score 4)
    "crisis": 3, "sanctions": 3, "ceasefire": 3, "layoffs": 3, "breach": 3, 
    "scandal": 3, "fatal": 3, "heatwave": 3, "wildfire": 3, "earthquake": 3,
    "collapse": 3, "data leak": 3, "charged": 3, "inflation": 3, "missile": 3, 
    "protests": 3, "subpoena": 3, "legislation": 3, "executive order": 3, "drought": 3,

    # Score 2 - 40 keywords (twice as many as Score 3)
    "ransomware": 2, "record profit": 2, "launch": 2, "leaked": 2, "clinical trial": 2,
    "vaccine": 2, "research study": 2, "IPO": 2, "quarterly report": 2, "greenhouse gases": 2,
    "pollution": 2, "mutation": 2, "demo": 2, "historic": 2, "job cuts": 2, 
    "staff layoffs": 2, "price hike": 2, "data breach": 2, "user privacy": 2, "stock drop": 2,
    "restructuring": 2, "debt crisis": 2, "tech failure": 2, "displacement": 2, "education cuts": 2,
    "income inequality": 2, "unemployment": 2, "climate change": 2, "financial crash": 2,
    "geopolitical tensions": 2, "trade war": 2, "cybersecurity breach": 2, "political crisis": 2,

    # Score 1 - 80 keywords (twice as many as Score 2)
    "small business growth": 1, "IPO filing": 1, "quarterly earnings": 1, "market trends": 1, 
    "new product launch": 1, "industry growth": 1, "innovation in tech": 1, "startup investment": 1,
    "consumer demand": 1, "patent filing": 1, "social media trends": 1, "digital marketing": 1, 
    "cloud technology": 1, "wearables": 1, "artificial intelligence": 1, "robotics": 1, 
    "nanotechnology": 1, "space exploration": 1, "green tech": 1, "renewable energy": 1, 
    "electronic vehicles": 1, "machine learning": 1, "quantum computing": 1, "big data": 1, 
    "blockchain": 1, "fintech": 1, "mobile apps": 1, "cloud computing": 1, "edge computing": 1,
    "5G technology": 1, "augmented reality": 1, "virtual reality": 1, "telemedicine": 1,
    "smart cities": 1, "e-commerce": 1, "data analytics": 1, "cryptocurrency": 1, "bitcoin": 1,
    "cryptocurrency mining": 1, "financial tech": 1, "self-driving cars": 1, "clean energy": 1,
    "smartphones": 1, "app development": 1, "wearable tech": 1, "IoT": 1, "cloud services": 1,
    "virtual assistants": 1, "privacy tech": 1, "sustainability": 1, "3D printing": 1
}
BASE_DIR = os.path.dirname(__file__)
SCORED_TOPICS_CSV = os.path.join(BASE_DIR, "scored_topics.csv")

# Load topic criticality
topic_criticality = {}
with open(SCORED_TOPICS_CSV, newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        if len(row) >= 2:
            topic_criticality[row[0].strip()] = int(row[1])

def normalize(text):
    words = text.lower().split()
    stemmed = [stemmer.stem(w) for w in words]
    lemmatized = [lemmatizer.lemmatize(w) for w in stemmed]
    return " ".join(lemmatized)

NORMALIZED_KEYWORDS = { normalize(k): v for k, v in KEYWORD_WEIGHTS.items() }

def score_text(text):
    norm_text = normalize(text)
    score = 0
    for keyword, weight in NORMALIZED_KEYWORDS.items():
        if keyword in norm_text:
            score += weight
    score += len(norm_text.split()) // 20
    return score

def combined_score(topic, article):
    return score_text(article["title"]) * topic_criticality.get(topic, 1)

def dedupe_articles(articles, threshold=0.75):
    unique = []
    for article in sorted(articles, key=lambda x: -x["score"]):
        if all(SequenceMatcher(None, normalize(article["title"]), normalize(seen["title"])).ratio() < threshold for seen in unique):
            unique.append(article)
    return unique

def to_eastern(dt):
    return dt.astimezone(ZoneInfo("America/New_York"))

LOCKFILE = "/tmp/digest_bot.lock"

if os.path.exists(LOCKFILE):
    print("Script is already running. Exiting.")
    sys.exit()
else:
    with open(LOCKFILE, 'w') as f:
        f.write("locked")

try:
    LOG_PATH = os.path.join(BASE_DIR, "logs/digest.log")
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO)
    logging.info(f"Script started at {datetime.now()}")

    EMAIL_FROM = os.getenv("GMAIL_USER", "").encode("ascii", "ignore").decode()
    EMAIL_TO = os.getenv("MAILTO", EMAIL_FROM).encode("ascii", "ignore").decode()
    SMTP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
    
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587

    TOPIC_CSV = SCORED_TOPICS_CSV  # Reuse the already-loaded path

    LAST_SEEN_FILE = os.path.join(BASE_DIR, "last_seen.json")

    if os.path.exists(LAST_SEEN_FILE):
        with open(LAST_SEEN_FILE, "r") as f:
            last_seen = json.load(f)
    else:
        last_seen = {}

    topics = list(topic_criticality.keys())

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
                    pubDate_dt = parsedate_to_datetime(pubDate).astimezone(ZoneInfo("America/New_York"))
                except:
                    pubDate_dt = None
                if not pubDate_dt or pubDate_dt <= one_week_ago.replace(tzinfo=ZoneInfo("UTC")):
                    continue
                score = combined_score(topic, {"title": title})
                if score >= 20:
                    topic_articles[topic].append({
                        "score": score,
                        "title": title,
                        "link": link,
                        "pubDate": pubDate
                    })
        except Exception as e:
            logging.warning(f"Error fetching topic '{topic}': {e}")
            continue
    topic_scores = [
       (topic, sum(article["score"] for article in articles) * topic_criticality.get(topic, 1))
        for topic, articles in topic_articles.items()
    ]
    top_topics = set(topic for topic, _ in sorted(topic_scores, key=lambda x: x[1], reverse=True)[:10])
    filtered_articles = {k: v for k, v in topic_articles.items() if k in top_topics}

    sent_articles = last_seen
    if filtered_articles:
        html_body = "<h2>Your News Digest</h2>"
        sections = []
        for topic, articles in filtered_articles.items():
            deduped = dedupe_articles(articles)
            topic_key = topic.replace(" ", "_").lower()
            raw_history = sent_articles.get(topic_key, [])
            if isinstance(raw_history, dict):
                raw_history = [raw_history]
            sent_articles[topic_key] = raw_history
            previous_titles = {
                normalize(a["title"]) for a in raw_history if isinstance(a, dict) and "title" in a
            }
            top_article = None
            for article in deduped:
                if normalize(article["title"]) not in previous_titles:
                    top_article = article
                    break
            if not top_article:
                continue
            raw_history.append({
                "title": top_article["title"],
                "pubDate": to_eastern(parsedate_to_datetime(top_article["pubDate"])).strftime('%a, %d %b %Y %I:%M %p %Z')
            })
            section_html = f"<h3>{html.escape(topic)}</h3>\n"
            section_html += f"""
            <p>
                📰 <a href=\"{top_article['link']}\" target=\"_blank\">{html.escape(top_article['title'])}</a><br>
                📅 {to_eastern(parsedate_to_datetime(top_article['pubDate'])).strftime('%a, %d %b %Y %I:%M %p %Z')} — Score: {top_article['score']}
            </p>
            """
            sections.append((top_article['score'], section_html))

        for _, html_section in sorted(sections, key=lambda x: -x[0]):
            html_body += html_section

        msg = EmailMessage()
        msg["Subject"] = f"🗞️ News Digest – {datetime.now().strftime('%Y-%m-%d') }"
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

    with open(LAST_SEEN_FILE, "w") as f:
        json.dump(sent_articles, f, indent=2)

finally:
    if os.path.exists(LOCKFILE):
        os.remove(LOCKFILE)
    logging.info(f"Lockfile released at {datetime.now()}")
