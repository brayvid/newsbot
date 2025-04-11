# Author: Blake Rayvid <https://github.com/brayvid/news-digest-bot>

# ─── Configurable Parameters ─────────────────────────────────────────────────

TREND_WEIGHT = 3                # 1–5: How much to boost a topic if it matches trending
TOPIC_WEIGHT = 2                # 1–5: Importance of `topics.csv` scores
KEYWORD_WEIGHT = 1              # 1–5: Importance of keyword scores 

MIN_ARTICLE_SCORE = 1           # Minimum combined score to include article
MAX_TOPICS = 20                 # Max number of topics to include in each digest
MAX_ARTICLES_PER_TOPIC = 1      # Max number of articles per topic in the digest
DEDUPLICATION_THRESHOLD = 0.7   # Similarity threshold for deduplication (0-1)

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
import random
from collections import defaultdict
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from nltk.stem import PorterStemmer, WordNetLemmatizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv

# Load topics.csv, keywords.csv and history.json
BASE_DIR = os.path.dirname(__file__)
TOPICS_CSV = os.path.join(BASE_DIR, "topics.csv")
KEYWORDS_CSV = os.path.join(BASE_DIR, "keywords.csv")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")

# Initialize logging immediately to capture all runtime info
log_path = os.path.join(BASE_DIR, "logs/digest_bot.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)
logging.basicConfig(filename=log_path, level=logging.INFO)
logging.info(f"Script started at {datetime.now()}")

stemmer = PorterStemmer()
lemmatizer = WordNetLemmatizer()
load_dotenv()

from nltk.data import find
import nltk
# Add the path just in case:
nltk.data.path.append("~/nltk-data")

def ensure_nltk_data():
    for resource in ['wordnet', 'omw-1.4']:
        try:
            find(f'corpora/{resource}')
        except LookupError:
            try:
                nltk.download(resource)
            except Exception as e:
                print(f"Failed to download {resource}: {e}")

ensure_nltk_data()

# Prevent concurrent runs using a lockfile
LOCKFILE = "/tmp/digest_bot.lock"
if os.path.exists(LOCKFILE):
    print("Script is already running. Exiting.")
    sys.exit()
else:
    with open(LOCKFILE, 'w') as f:
        f.write("locked")


def normalize(text):
    # Lowercases, stems, and lemmatizes words to produce normalized text for matching.
    words = text.lower().split()
    stemmed = [stemmer.stem(w) for w in words]
    lemmatized = [lemmatizer.lemmatize(w) for w in stemmed]
    return " ".join(lemmatized)

def load_topic_weights():
    # Loads topic weights from topics.csv into a dictionary
    weights = {}
    with open(TOPICS_CSV, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 2 or not row[0].strip() or not row[1].strip():
                continue
            try:
                weights[row[0].strip()] = int(row[1])
            except ValueError:
                logging.warning(f"Invalid topic weight for '{row[0].strip()}': {row[1]}")
    return weights

def load_keyword_weights():
    # Loads keyword weights from keywords.csv into a dictionary
    weights = {}
    with open(KEYWORDS_CSV, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 2 or not row[0].strip() or not row[1].strip():
                continue
            try:
                weights[row[0].strip().lower()] = int(row[1])
            except ValueError:
                logging.warning(f"Invalid keyword weight for '{row[0].strip()}': {row[1]}")
    return weights

KEYWORD_WEIGHTS = load_keyword_weights()
NORMALIZED_KEYWORDS = { normalize(k): v for k, v in KEYWORD_WEIGHTS.items() }

def score_text(text):
    # Scores a text by summing keyword weights and a small bonus for length
    norm_text = normalize(text)
    score = 0
    for keyword, weight in NORMALIZED_KEYWORDS.items():
        if keyword in norm_text:
            score += weight
    score += len(norm_text.split()) // 20
    return score

def fetch_google_top_headlines(max_articles=50):
    # Fetches up to N top headlines from Google News RSS (US edition) within the past week
    url = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        items = root.findall("./channel/item")

        one_week_ago = datetime.now(ZoneInfo("America/New_York")) - timedelta(days=7)
        articles = []

        for item in items:
            title = item.findtext("title") or "No title"
            link = item.findtext("link")
            pub_date = item.findtext("pubDate")

            try:
                pub_dt = parsedate_to_datetime(pub_date).astimezone(ZoneInfo("America/New_York"))
            except:
                continue

            if pub_dt <= one_week_ago:
                continue

            articles.append({
                "title": title,
                "link": link,
                "pubDate": pub_date,
                "pub_dt": pub_dt
            })

            if len(articles) >= max_articles:
                break

        logging.info(f"Fetched {len(articles)} top headlines from Google News RSS.")
        return articles

    except Exception as e:
        logging.warning(f"Failed to fetch Google top headlines: {e}")
        return []

def fetch_articles_for_topic(topic, topic_weights, keyword_weights):
    # Searches Google News RSS for a topic and returns articles with calculated scores
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(topic)}"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        one_week_ago = datetime.now(ZoneInfo("America/New_York")) - timedelta(days=7)
        articles = []

        for item in root.findall("./channel/item"):
            title = item.findtext("title") or "No title"
            link = item.findtext("link")
            pubDate = item.findtext("pubDate")

            try:
                pub_dt = parsedate_to_datetime(pubDate).astimezone(ZoneInfo("America/New_York"))
            except Exception:
                pub_dt = None

            if not pub_dt or pub_dt <= one_week_ago:
                continue

            score, topic_scores = match_article_to_topics(title, topic_weights, keyword_weights)
            total_score = score + sum(topic_scores.values())

            if total_score >= MIN_ARTICLE_SCORE:
                articles.append({
                    "title": title,
                    "link": link,
                    "pubDate": pubDate,
                    "pub_dt": pub_dt,  # include this for efficient scoring later
                    "score": total_score
                })
        logging.info(f"Found {len(articles)} articles for topic '{topic}'")
        return articles

    except Exception as e:
        logging.warning(f"Failed to fetch articles for topic '{topic}': {e}")
        return []

def match_article_to_topics(article_title, topic_weights, keyword_weights):
    # Evaluates topic and keyword relevance of an article title; returns total score and per-topic match scores
    score = 0
    normalized_title = normalize(article_title)

    for keyword, weight in keyword_weights.items():
        if keyword in normalized_title:
            score += weight * KEYWORD_WEIGHT
            logging.debug(f"Keyword match: '{keyword}' in '{article_title}'")

    topic_match_scores = {}
    for topic, weight in topic_weights.items():
        normalized_topic = normalize(topic)
        similarity = SequenceMatcher(None, normalized_title, normalized_topic).ratio()

        if similarity > DEDUPLICATION_THRESHOLD:
            topic_score = weight * TOPIC_WEIGHT
            topic_match_scores[topic] = topic_score
            logging.info(f"Trending match: '{article_title}' ≈ '{topic}' (sim={similarity:.2f})")

    total_topic_score = sum(topic_match_scores.values())
    return score + total_topic_score, topic_match_scores

def combined_score(topic, article, topic_weights):
    # Calculates final article score combining keyword relevance, topic weight, and a recency bonus.
    keyword_score = score_text(article["title"]) * KEYWORD_WEIGHT
    topic_score = topic_weights.get(topic, 1) * TOPIC_WEIGHT
    pub_dt = article.get("pub_dt")
    recency_score = 5 if pub_dt and pub_dt > datetime.now(ZoneInfo("America/New_York")) - timedelta(days=1) else 1
    return (keyword_score + topic_score) * recency_score

def dedupe_articles(articles, threshold=DEDUPLICATION_THRESHOLD):
    # Removes articles with similar titles above a similarity threshold
    unique_articles = []
    for article in sorted(articles, key=lambda x: -x['score']):
        if all(SequenceMatcher(None, normalize(article['title']), normalize(seen['title'])).ratio() < threshold for seen in unique_articles):
            unique_articles.append(article)
    return unique_articles

def is_in_history(article_title, topic_key, history):
    # Checks if a normalized article title is already in the history for a topic
    norm_title = normalize(article_title)
    return any(normalize(a["title"]) == norm_title for a in history.get(topic_key, []))

def to_eastern(dt):
    # Converts datetime to US Eastern Timezone
    return dt.astimezone(ZoneInfo("America/New_York"))

# Main logic: fetch trending headlines, identify strong topic matches, fetch and score articles, deduplicate and filter, and send the digest email.
def main():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
    else:
        history = {}

    try:
        topic_weights = load_topic_weights()
        keyword_weights = load_keyword_weights()
        normalized_topics = {normalize(t): t for t in topic_weights}

        # Step 1: Get latest headlines and boost matching topics
        latest_articles = fetch_google_top_headlines()
        trending_boosts = defaultdict(int)

        for article in latest_articles:
            title = article.get("title", "")
            if not title:
                continue
            norm_title = normalize(title)
            keyword_score = score_text(title)

            for norm_topic, raw_topic in normalized_topics.items():
                similarity = SequenceMatcher(None, norm_title, norm_topic).ratio()
                if similarity > DEDUPLICATION_THRESHOLD:
                    trending_boosts[raw_topic] += TREND_WEIGHT + keyword_score // 10
                    logging.info(f"Trending boost: '{title}' ≈ '{raw_topic}' (sim={similarity:.2f})")

        topic_sources = {}

        for topic, boost in trending_boosts.items():
            topic_weights[topic] += boost
            topic_sources[topic] = "latest"

        # Step 2: Build limited topic list to fetch
        topics_to_fetch = set(trending_boosts.keys())
        remaining_slots = MAX_TOPICS - len(topics_to_fetch)

        if remaining_slots > 0:
            fallback_candidates = sorted(
                (t for t in topic_weights if t not in topics_to_fetch),
                key=lambda t: -topic_weights[t]
            )
            for t in fallback_candidates:
                topics_to_fetch.add(t)
                topic_sources[t] = "user"
                if len(topics_to_fetch) >= MAX_TOPICS:
                    break

        # Step 3: Fetch articles only for selected topics
        all_articles = {}
        for topic in topics_to_fetch:
            articles = fetch_articles_for_topic(topic, topic_weights, keyword_weights)
            if articles:
                deduped = dedupe_articles(articles)
                for a in deduped:
                    a["score"] = combined_score(topic, a, topic_weights)
                all_articles[topic] = sorted(deduped, key=lambda x: -x["score"])

        # Debug log
        # for topic, arts in all_articles.items():
        #     logging.info(f"Topic '{topic}' has {len(arts)} scored articles. Top score: {arts[0]['score'] if arts else 'N/A'}")

        # Step 4: Score and prioritize topics for the digest
        digest_topics = sorted(
            [(t, sum(a["score"] for a in all_articles.get(t, [])))
             for t in topics_to_fetch if all_articles.get(t)],
            key=lambda x: -x[1]
        )[:MAX_TOPICS]

        digest = {}
        for topic, _ in digest_topics:
            # Get sorted & deduped articles for this topic
            articles = all_articles.get(topic, [])

            # Filter out articles that have already been emailed
            topic_key = topic.replace(" ", "_").lower()
            seen_titles = {normalize(a["title"]) for a in history.get(topic_key, [])}
            articles = [a for a in articles if normalize(a["title"]) not in seen_titles]

            if not articles:
                continue
            
            # Introduce small variation to get fresh combos
            start_index = random.randint(0, min(2, len(articles) - 1))
            articles = articles[start_index:start_index + 5]

            # TFIDF deduplication
            titles = [a["title"] for a in articles]
            tfidf = TfidfVectorizer().fit_transform(titles)
            sim_matrix = cosine_similarity(tfidf)

            # Select top-scoring articles for this topic, ensuring low similarity and capping at MAX_ARTICLES_PER_TOPIC
            selected = []
            for i in range(len(articles)):
                if len(selected) >= MAX_ARTICLES_PER_TOPIC:
                    break
                if i == 0 or all(sim_matrix[i][j] < DEDUPLICATION_THRESHOLD for j in range(i)):
                    selected.append(articles[i])

            digest[topic] = selected

        # logging.info(f"Digest content: {json.dumps(digest, indent=2, default=str)}")

        if not digest:
            logging.info("No articles met criteria. Skipping email.")
            return

        # Step 5: Compose and send email
        EMAIL_FROM = os.getenv("GMAIL_USER", "").encode("ascii", "ignore").decode()
        EMAIL_TO = os.getenv("MAILTO", EMAIL_FROM).encode("ascii", "ignore").decode()
        SMTP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
        SMTP_SERVER = "smtp.gmail.com"
        SMTP_PORT = 587

        html_body = "<h2>Your News</h2>"
        for topic, articles in sorted(digest.items(), key=lambda x: -sum(a['score'] for a in x[1])):
            
            section = f'<h3 style="margin: 0 0 0 0;">{html.escape(topic)}</h3>'
            for article in articles:
                pub_dt = to_eastern(parsedate_to_datetime(article["pubDate"]))
                section += (
                    f'<p style="margin: 0.4em 0 1.2em 0;">'
                    f'📰 <a href="{article["link"]}" target="_blank">{html.escape(article["title"])}</a><br>'
                    f'<span style="font-size: 0.9em;">📅 {pub_dt.strftime("%a, %d %b %Y %I:%M %p %Z")} — Score: {article["score"]}</span>'
                    f'</p>'
                )

            html_body += section

        config_code = f"(Trend weight: {TREND_WEIGHT}, Topic Weight: {TOPIC_WEIGHT}, Keyword Weight: {KEYWORD_WEIGHT}, Min Score: {MIN_ARTICLE_SCORE}, Max Similarity: {DEDUPLICATION_THRESHOLD}, Topics: {MAX_TOPICS})"
        html_body += f"<hr><small>{config_code}</small>"

        msg = EmailMessage()
        msg["Subject"] = f"🗞️ News – {datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %I:%M %p %Z')}"
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

            for topic, articles in digest.items():
                key = topic.replace(" ", "_").lower()
                if key not in history:
                    history[key] = []
                existing_titles = {normalize(a["title"]) for a in history[key]}
                for article in articles:
                    if normalize(article["title"]) not in existing_titles:
                        history[key].append({
                            "title": article["title"],
                            "pubDate": article["pubDate"]
                        })
                history[key] = history[key][-40:]

        except Exception as e:
            logging.error(f"Email failed: {e}")

        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)

    finally:
        if os.path.exists(LOCKFILE):
            os.remove(LOCKFILE)
        logging.info(f"Lockfile released at {datetime.now()}")

if __name__ == "__main__":
    main()




