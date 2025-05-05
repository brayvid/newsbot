# Author: Blake Rayvid <https://github.com/brayvid/newsbot>

import os
import sys

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

BASE_DIR = os.path.dirname(__file__)

# Prevent concurrent runs using a lockfile
LOCKFILE = os.path.join(BASE_DIR, "newsbot.lock")
if os.path.exists(LOCKFILE):
    print("Script is already running. Exiting.")
    sys.exit()
else:
    with open(LOCKFILE, 'w') as f:
        f.write("locked")

import csv
import smtplib
import html
import logging
import shutil
import json
import re
from datetime import datetime, timedelta
from email.message import EmailMessage
import xml.etree.ElementTree as ET
import requests
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from nltk.stem import PorterStemmer, WordNetLemmatizer
from dotenv import load_dotenv
import google.generativeai as genai

HISTORY_FILE = os.path.join(BASE_DIR, "history.json")

# Initialize logging immediately to capture all runtime info
log_path = os.path.join(BASE_DIR, "logs/newsbot.log")
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

# Configuration files in Google Sheets
TOPICS_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTWCrmL5uXBJ9_pORfhESiZyzD3Yw9ci0Y-fQfv0WATRDq6T8dX0E7yz1XNfA6f92R7FDmK40MFSdH4/pub?gid=0&single=true&output=csv"
KEYWORDS_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTWCrmL5uXBJ9_pORfhESiZyzD3Yw9ci0Y-fQfv0WATRDq6T8dX0E7yz1XNfA6f92R7FDmK40MFSdH4/pub?gid=314441026&single=true&output=csv"
OVERRIDES_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTWCrmL5uXBJ9_pORfhESiZyzD3Yw9ci0Y-fQfv0WATRDq6T8dX0E7yz1XNfA6f92R7FDmK40MFSdH4/pub?gid=1760236101&single=true&output=csv"
CONFIG_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTWCrmL5uXBJ9_pORfhESiZyzD3Yw9ci0Y-fQfv0WATRDq6T8dX0E7yz1XNfA6f92R7FDmK40MFSdH4/pub?gid=446667252&single=true&output=csv"

# Loads key-value config settings from a CSV Google Sheet URL.
def load_config_from_sheet(url):
    config = {}
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        lines = response.text.splitlines()
        reader = csv.reader(lines)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) >= 2:
                key = row[0].strip()
                val = row[1].strip()
                try:
                    if '.' in val:
                        config[key] = float(val)
                    else:
                        config[key] = int(val)
                except ValueError:
                    config[key] = val  # fallback to string
    except Exception as e:
        logging.warning(f"Failed to load config from Google Sheet: {e}")
    return config

CONFIG = load_config_from_sheet(CONFIG_URL)

MAX_ARTICLE_AGE = int(CONFIG.get("MAX_ARTICLE_AGE", 6))
MAX_TOPICS = int(CONFIG.get("MAX_TOPICS", 7))
MAX_ARTICLES_PER_TOPIC = int(CONFIG.get("MAX_ARTICLES_PER_TOPIC", 1))
DEMOTE_FACTOR = CONFIG.get("DEMOTE_FACTOR",0.5)

def load_csv_weights(url):
    weights = {}
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        lines = response.text.splitlines()
        reader = csv.reader(lines)
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                try:
                    weights[row[0].strip()] = int(row[1])
                except ValueError:
                    continue
    except Exception as e:
        logging.warning(f"Failed to load weights from {url}: {e}")
    return weights

def load_overrides(url):
    overrides = {}
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        reader = csv.reader(response.text.splitlines())
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                overrides[row[0].strip().lower()] = row[1].strip().lower()
    except Exception as e:
        logging.warning(f"Failed to load overrides: {e}")
    return overrides

# Lowercases, stems, and lemmatizes words to produce normalized text for matching.
def normalize(text):
    words = text.lower().split()
    stemmed = [stemmer.stem(w) for w in words]
    lemmatized = [lemmatizer.lemmatize(w) for w in stemmed]
    return " ".join(lemmatized)

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

def fetch_articles_for_topic(topic, max_age_days=1):
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(topic)}"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        time_cutoff = datetime.now(ZoneInfo("America/New_York")) - timedelta(hours=MAX_ARTICLE_AGE)
        articles = []

        for item in root.findall("./channel/item"):
            title = item.findtext("title") or "No title"
            link = item.findtext("link")
            pubDate = item.findtext("pubDate")
            try:
                pub_dt = parsedate_to_datetime(pubDate).astimezone(ZoneInfo("America/New_York"))
            except:
                continue
            if pub_dt <= time_cutoff:
                continue
            articles.append({"title": title, "link": link, "pubDate": pubDate})
        return articles
    except Exception as e:
        logging.warning(f"Failed to fetch articles for {topic}: {e}")
        return []

def build_user_preferences(topics, keywords, overrides):
    """
    Build a structured string representing the user's topic/keyword preferences
    and overrides, preserving importance scores.
    """
    preferences = []

    if topics:
        preferences.append("User topics (ranked 1-5 in importance):")
        for topic, score in sorted(topics.items(), key=lambda x: -x[1]):
            preferences.append(f"- {topic}: {score}")

    if keywords:
        preferences.append("\nHeadline keywords (ranked 1-5 in importance):")
        for keyword, score in sorted(keywords.items(), key=lambda x: -x[1]):
            preferences.append(f"- {keyword}: {score}")

    banned = [k for k, v in overrides.items() if v == "ban"]
    demoted = [k for k, v in overrides.items() if v == "demote"]

    if banned:
        preferences.append("\nBanned terms (must not appear in topics or headlines):")
        for term in banned:
            preferences.append(f"- {term}")

    if demoted:
        preferences.append(f"\nDemoted terms (consider headlines with these terms {DEMOTE_FACTOR} times as important to user):")
        for term in demoted:
            preferences.append(f"- {term}")

    return "\n".join(preferences)

def safe_parse_json(raw: str) -> dict:
    # Strip markdown fences
    if raw.strip().startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())

    # Repair common malformed endings like extra closing brackets
    # Remove trailing ] if it's immediately after a closing brace
    raw = re.sub(r"\}\s*\]$", "}", raw.strip())

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logging.error("Failed to parse Gemini response.")
        logging.error(raw)
        raise ValueError("Gemini returned malformed JSON:\n" + repr(raw)) from e

def prioritize_with_gemini(topics_to_headlines: dict, user_preferences: str, gemini_api_key: str) -> dict:
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel(model_name="models/gemini-2.0-flash-lite-001")

    prompt = (
        "You are choosing news topics and headlines most relevant to a user to include in a digest based on their preferences.\n"
        f"Given a dictionary of topics and corresponding headlines, and the user's preferences, select up to {MAX_TOPICS} of the most important topics today.\n"
        f"For each selected topic, return the top {MAX_ARTICLES_PER_TOPIC} most important headlines.\n"
        "Be careful to avoid returning multiple of the same or similar headlines that cover roughly the same thing.\n"
        "Respect the user's importance preferences for topics and keywords as indicated with a score of 1-5, with 5 the highest."
        "Be sure not to include any headlines containing any banned terms as indicated by 'banned' in the user preferences, and demote headlines containing keywords flagged 'demote'."
        "There should be a healthy diversity of subjects covered by your recommendations, not focused on one."
        "Be very careful to respond ONLY with *VALID JSON* like:\n"
        "{ \"Technology\": [\"Headline A\", \"Headline B\"], \"Climate\": [\"Headline C\"] }\n\n"
        f"User Preferences:\n{user_preferences}\n\n"
        f"Topics and Headlines:\n{json.dumps(dict(sorted(topics_to_headlines.items())), indent=2)}\n"

    )
    # print(prompt)
    response = model.generate_content([prompt])
    raw = getattr(response, "text", None)

    # Handle Markdown-wrapped JSON like ```json\n{...}\n```
    if raw and raw.strip().startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())  # remove opening ```
        raw = re.sub(r"\s*```$", "", raw.strip())          # remove closing ```

    try:
        return safe_parse_json(raw)
    except Exception:
        raise ValueError("Gemini returned invalid JSON or no content:\n" + repr(raw))


# Main logic: fetch trending headlines, identify strong topic matches, fetch and score articles, deduplicate and filter, and send the digest email.
def main():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
    else:
        history = {}

    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            logging.error("Missing GEMINI_API_KEY. Exiting.")
            return

        topic_weights = load_csv_weights(TOPICS_CSV_URL)
        keyword_weights = load_csv_weights(KEYWORDS_CSV_URL)
        overrides = load_overrides(OVERRIDES_CSV_URL)

        user_preferences = build_user_preferences(topic_weights, keyword_weights, overrides)

        # Fetch all articles for all topics
        topics_to_headlines = {}
        full_articles = {}
        for topic in topic_weights:
            articles = fetch_articles_for_topic(topic)
            if articles:
                # Filter out articles already seen in history
                fresh_articles = [a for a in articles if not is_in_history(a["title"], history)]
                if fresh_articles:
                    topics_to_headlines[topic] = [a["title"] for a in fresh_articles]
                    full_articles[topic] = fresh_articles


        if not topics_to_headlines:
            logging.info("No headlines available for LLM input.")
            return

        total_headlines = sum(len(v) for v in topics_to_headlines.values())
        logging.info(f"Sending {total_headlines} headlines across {len(topics_to_headlines)} topics to Gemini.")

        # Get prioritized digest from Gemini
        digest_titles = prioritize_with_gemini(topics_to_headlines, user_preferences, gemini_api_key)

        # Rebuild full article entries for final digest
        digest = {}
        for topic, titles in digest_titles.items():
            articles = full_articles.get(topic, [])
            selected = []
            seen_titles = set()
            for title in titles:
                for a in articles:
                    if normalize(a["title"]) == normalize(title) and normalize(title) not in seen_titles:
                        selected.append(a)
                        seen_titles.add(normalize(title))
                        break
            if selected:
                digest[topic] = selected

        if not digest:
            logging.info("Gemini returned no digest-worthy content.")
            return

        # Step 5: Compose and send email
        EMAIL_FROM = os.getenv("GMAIL_USER", "").encode("ascii", "ignore").decode()
        EMAIL_TO = EMAIL_FROM
        EMAIL_BCC = os.getenv("MAILTO", "").strip()
        EMAIL_BCC_LIST = [email.strip() for email in EMAIL_BCC.split(",") if email.strip()]
        SMTP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
        SMTP_SERVER = "smtp.gmail.com"
        SMTP_PORT = 587

        html_body = "<h2>Your News</h2>"
        for topic, articles in digest.items():
            section = f'<h3 style="margin: 0 0 0 0;">{html.escape(topic)}</h3>'
            for article in articles:
                pub_dt = to_eastern(parsedate_to_datetime(article["pubDate"]))
                section += (
                    f'<p style="margin: 0.4em 0 1.2em 0;">'
                    f'📰 <a href="{article["link"]}" target="_blank">{html.escape(article["title"])}</a><br>'
                    f'<span style="font-size: 0.9em;">📅 {pub_dt.strftime("%a, %d %b %Y %I:%M %p %Z")}</span>'
                    f'</p>'
                )
            html_body += section

        msg = EmailMessage()
        msg["Subject"] = f"🗞️ News – {datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %I:%M %p %Z')}"
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg["Bcc"] = ", ".join(EMAIL_BCC_LIST)
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

        # Delete ~/nltk_data directory if it exists
        nltk_path = os.path.expanduser("~/nltk_data")
        if os.path.exists(nltk_path):
            try:
                shutil.rmtree(nltk_path)
                # logging.info("Deleted ~/nltk_data directory after run.")
            except Exception as e:
                logging.warning(f"Failed to delete ~/nltk_data: {e}")

if __name__ == "__main__":
    main()
