# Author: Blake Rayvid <https://github.com/brayvid/news-digest-bot>

# ─── Configurable Parameters ─────────────────────────────────────────────────
TREND_WEIGHT = 1                # 1–5: How much to boost a topic if it matches trending
TOPIC_WEIGHT = 1                # 1–5: Importance of `topics.csv` scores
KEYWORD_WEIGHT = 1              # 1–5: Importance of keyword scores 

MIN_ARTICLE_SCORE = 1           # Minimum combined score to include article
MAX_TOPICS = 7                  # Max number of topics to include in each digest
MAX_ARTICLES_PER_TOPIC = 1      # Max number of articles per topic in the digest

DEDUPLICATION_THRESHOLD = 0.2   # 0-1: Similarity threshold for deduplication (0-1)
TREND_OVERLAP_THRESHOLD = 0.2   # 0–1: Min token overlap for a headline to match a topic

CATEGORY_ACTIONS = {
    "sports": "ban",
    "entertainment": "demote",
    "daily mail": "ban",
    "fox news": "ban",
    "celebrity": "demote",
    "fifa": "ban",
    "baseball": "ban",
    "mlb": "ban",
    "nba": "ban",
    "nfl": "ban",
    "football": "ban",
    "basketball":"ban",
    "cosmopolitan":"ban",
    "entertainment weekly": "ban",
    "espn":"ban",
    "us weekly": "ban",
    "vogue":"ban",
    "golf":"ban",
    "food":"ban",
    "local":"demote",
    "county":"demote",
    "town":"demote"
}

DEMOTE_FACTOR = 0.5 

import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

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
import random
import math
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

# Download nltk resources
from nltk.data import find
import nltk
nltk.data.path.append("~/nltk_data")

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

# Lowercases, stems, and lemmatizes words to produce normalized text for matching.
def normalize(text):
    words = text.lower().split()
    stemmed = [stemmer.stem(w) for w in words]
    lemmatized = [lemmatizer.lemmatize(w) for w in stemmed]
    return " ".join(lemmatized)

def load_topic_weights():
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
                continue
    return weights

def load_keyword_weights():
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
                continue
    return weights

KEYWORD_WEIGHTS = load_keyword_weights()
NORMALIZED_KEYWORDS = { normalize(k): v for k, v in KEYWORD_WEIGHTS.items() }

def score_text(text):
    norm_text = normalize(text)
    score = 0

    # Add scores based on keyword matches
    for keyword, weight in NORMALIZED_KEYWORDS.items():
        if keyword in norm_text:
            score += weight

    word_count = len(norm_text.split())

    # Boost: longer headlines get a slight bonus
    long_title_bonus = 1.0 + min(word_count / 30.0, 0.3)

    score = score * long_title_bonus
    return score


# Fetches up to N top headlines from Google News RSS (US edition) within the past week
def fetch_google_top_headlines(max_articles=50):
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

        return articles

    except Exception:
        return []

def fetch_articles_for_topic(topic, topic_weights, keyword_weights):
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
            except:
                pub_dt = None

            if not pub_dt or pub_dt <= one_week_ago:
                continue

            articles.append({
                "title": title,
                "link": link,
                "pubDate": pubDate,
                "pub_dt": pub_dt
            })

        return articles

    except Exception:
        return []
# Evaluates topic and keyword relevance of an article title; returns total score and per-topic match scores
def match_article_to_topics(article_title, topic_weights, keyword_weights):
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
            # Debugging
            # logging.info(f"Trending match: '{article_title}' ≈ '{topic}' (sim={similarity:.2f})")

    total_topic_score = sum(topic_match_scores.values())
    return score + total_topic_score, topic_match_scores

# Calculates final article score combining keyword relevance, topic weight, and a recency bonus.
def combined_score(topic, article, topic_weights):
    topic_key = topic.lower()
    importance = 1.0  # Default importance factor

    # Normalize title once
    normalized_title = normalize(article["title"])

    # Ban based on banned keywords inside the title
    for banned_word, action in CATEGORY_ACTIONS.items():
        if action == "ban" and banned_word in normalized_title:
            return 0

    # Demote or ban based on topic
    action = CATEGORY_ACTIONS.get(topic_key)
    if action == "ban":
        return 0
    elif action == "demote":
        importance *= DEMOTE_FACTOR

    keyword_score = score_text(article["title"]) * KEYWORD_WEIGHT
    topic_score = topic_weights.get(topic, 1) * TOPIC_WEIGHT
    recency_score = 5 if article.get("pub_dt") and article["pub_dt"] > datetime.now(ZoneInfo("America/New_York")) - timedelta(hours=6) else 1

    total_score = (keyword_score + topic_score) * recency_score * importance
    return total_score

# Removes articles with similar titles above a similarity threshold
def dedupe_articles(articles, threshold=DEDUPLICATION_THRESHOLD):
    if len(articles) <= 1:
        return articles

    titles = [normalize(a["title"]) for a in articles]
    tfidf = TfidfVectorizer().fit_transform(titles)
    sim_matrix = cosine_similarity(tfidf)

    selected_indices = []
    for i in range(len(articles)):
        if all(sim_matrix[i][j] < threshold for j in selected_indices):
            selected_indices.append(i)

    deduped_articles = [articles[i] for i in selected_indices]
    return deduped_articles

# Checks if a normalized article title is already in history.json
def is_in_history(article_title, history):
    norm_title = normalize(article_title)
    for articles in history.values():
        if any(normalize(a["title"]) == norm_title for a in articles):
            return True
    return False

# Converts datetime to US Eastern Timezone
def to_eastern(dt): 
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
            title_tokens = set(norm_title.split())
            keyword_score = score_text(title)

            for norm_topic, raw_topic in normalized_topics.items():
                topic_tokens = set(norm_topic.split())
                if not topic_tokens:
                    continue

                overlap = len(title_tokens & topic_tokens) / len(topic_tokens)
                if overlap >= TREND_OVERLAP_THRESHOLD:
                    trending_boosts[raw_topic] += TREND_WEIGHT * (1 + keyword_score / 10)

        # Debugging
        # logging.info(f"Trending boosts: {list(trending_boosts)}")
        topic_sources = {}

        # Apply boosts to a copy of the topic weights
        boosted_topic_weights = topic_weights.copy()
        for topic, boost in trending_boosts.items():
            boosted_topic_weights[topic] = boosted_topic_weights.get(topic, 0) + boost
            topic_sources[topic] = "latest"

        # Step 2: Build limited topic list to fetch
        topics_to_fetch = set(trending_boosts.keys())
        remaining_slots = MAX_TOPICS - len(topics_to_fetch)

        if remaining_slots > 0:
            fallback_candidates = [t for t in boosted_topic_weights if t not in topics_to_fetch]
            random.shuffle(fallback_candidates)
            fallback_candidates.sort(key=lambda t: -boosted_topic_weights[t])

            for t in fallback_candidates:
                topics_to_fetch.add(t)
                topic_sources[t] = "user"
                if len(topics_to_fetch) >= MAX_TOPICS:
                    break
        
        # Debugging
        # logging.info(f"Boosted topic weights: {sorted(boosted_topic_weights.items(), key=lambda x: -x[1])}")
        # logging.info(f"Selected topics for fetch: {list(topics_to_fetch)}")

        # Step 3: Fetch articles only for selected topics
        all_articles = {}
        for topic in topics_to_fetch:
            articles = fetch_articles_for_topic(topic, boosted_topic_weights, keyword_weights)
            if articles:
                deduped = dedupe_articles(articles)
                for a in deduped:
                    a["score"] = combined_score(topic, a, boosted_topic_weights)
                all_articles[topic] = sorted(deduped, key=lambda x: -x["score"])

        # Debugging
        # for topic, arts in all_articles.items():
        #     logging.info(f"Topic '{topic}' has {len(arts)} scored articles. Top score: {arts[0]['score'] if arts else 'N/A'}")

        # Step 4: Score and prioritize topics for the digest
        digest_topics = sorted(
            [(t, sum(a["score"] for a in all_articles.get(t, [])))
             for t in topics_to_fetch if all_articles.get(t)],
            key=lambda x: -x[1]
        )[:MAX_TOPICS]

        digest = {}
        selected_titles = set()  # track selected articles globally across topics

        for topic, _ in digest_topics:
            # Get sorted & deduped articles for this topic
            articles = all_articles.get(topic, [])

            # Filter out articles that have already been emailed or already selected
            articles = [
                a for a in articles
                if normalize(a["title"]) not in selected_titles and not is_in_history(a["title"], history)
            ]

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

            # After selecting articles, add them to selected_titles
            for article in selected:
                selected_titles.add(normalize(article["title"]))

            digest[topic] = selected


        # Debugging
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
                    f'<span style="font-size: 0.9em;">📅 {pub_dt.strftime("%a, %d %b %Y %I:%M %p %Z")} — Score: {math.floor(article["score"])}</span>'
                    f'</p>'
                )

            html_body += section

        config_code = f"(Trend weight: {TREND_WEIGHT}, Topic Weight: {TOPIC_WEIGHT}, Keyword Weight: {KEYWORD_WEIGHT}, Min Article Score: {MIN_ARTICLE_SCORE}, Max Topics: {MAX_TOPICS}, Trend Threshold: {TREND_OVERLAP_THRESHOLD}, Similarity Threshold: {DEDUPLICATION_THRESHOLD})"
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




