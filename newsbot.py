# Author: Blake Rayvid <https://github.com/brayvid/newsbot>

import os
import sys
import subprocess # Added for git operations

# Define paths and URLs for local files and remote configuration.
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # Ensure BASE_DIR is absolute
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")

CONFIG_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTWCrmL5uXBJ9_pORfhESiZyzD3Yw9ci0Y-fQfv0WATRDq6T8dX0E7yz1XNfA6f92R7FDmK40MFSdH4/pub?gid=446667252&single=true&output=csv"
TOPICS_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTWCrmL5uXBJ9_pORfhESiZyzD3Yw9ci0Y-fQfv0WATRDq6T8dX0E7yz1XNfA6f92R7FDmK40MFSdH4/pub?gid=0&single=true&output=csv"
KEYWORDS_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTWCrmL5uXBJ9_pORfhESiZyzD3Yw9ci0Y-fQfv0WATRDq6T8dX0E7yz1XNfA6f92R7FDmK40MFSdH4/pub?gid=314441026&single=true&output=csv"
OVERRIDES_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTWCrmL5uXBJ9_pORfhESiZyzD3Yw9ci0Y-fQfv0WATRDq6T8dX0E7yz1XNfA6f92R7FDmK40MFSdH4/pub?gid=1760236101&single=true&output=csv"

# Prevent concurrent runs using a lockfile
LOCKFILE = os.path.join(BASE_DIR, "newsbot.lock")
if os.path.exists(LOCKFILE):
    print("Script is already running. Exiting.")
    sys.exit()
else:
    with open(LOCKFILE, 'w') as f:
        f.write("locked")

# Import all required libraries
import csv
import smtplib
import html
import logging
import time
import random
import json
import re
import ast
from datetime import datetime, timedelta
from email.message import EmailMessage
import xml.etree.ElementTree as ET
import requests
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from nltk.stem import PorterStemmer, WordNetLemmatizer
from dotenv import load_dotenv # Keep this early
import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool # Added
from proto.marshal.collections.repeated import RepeatedComposite # Added
from proto.marshal.collections.maps import MapComposite # Added


# Load environment variables from .env file FIRST.
load_dotenv()

# Initialize logging immediately to capture all runtime info
log_path = os.path.join(BASE_DIR, "logs/newsbot.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)
logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.info(f"Script started at {datetime.now()}")

# Initialize NLP tools.
stemmer = PorterStemmer()
lemmatizer = WordNetLemmatizer()


# Download nltk resources
from nltk.data import find
import nltk

def ensure_nltk_data():
    nltk_home_dir = os.path.expanduser("~/nltk_data")
    download_target_dir = nltk_home_dir 
    if download_target_dir not in nltk.data.path:
        nltk.data.path.append(download_target_dir)
    os.makedirs(download_target_dir, exist_ok=True)

    for resource in ['wordnet', 'omw-1.4']:
        try: 
            find(f'corpora/{resource}')
            logging.info(f"NLTK resource '{resource}' found.")
        except LookupError:
            try:
                logging.info(f"Downloading NLTK resource: {resource} to {download_target_dir}")
                nltk.download(resource, download_dir=download_target_dir)
            except Exception as e:
                logging.error(f"Failed to download NLTK resource {resource}: {e}")

ensure_nltk_data()

# Loads key-value config settings from a CSV Google Sheet URL.
def load_config_from_sheet(url):
    config = {}
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        lines = response.text.splitlines()
        reader = csv.reader(lines)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) >= 2:
                key = row[0].strip()
                val = row[1].strip()
                try:
                    if '.' in val and not val.startswith('0.') and val.count('.') == 1:
                        config[key] = int(float(val)) if float(val) == int(float(val)) else float(val)
                    else:
                        config[key] = int(val)
                except ValueError:
                    if val.lower() == 'true': config[key] = True
                    elif val.lower() == 'false': config[key] = False
                    else: config[key] = val
        return config
    except Exception as e:
        logging.error(f"Failed to load config from {url}: {e}")
        return None

# Load config before main
CONFIG = load_config_from_sheet(CONFIG_CSV_URL)
if CONFIG is None:
    logging.critical("Fatal: Unable to load CONFIG from sheet. Exiting.")
    if os.path.exists(LOCKFILE): os.remove(LOCKFILE)
    sys.exit(1)

MAX_ARTICLE_HOURS = int(CONFIG.get("MAX_ARTICLE_HOURS", 6))
MAX_TOPICS = int(CONFIG.get("MAX_TOPICS", 7))
MAX_ARTICLES_PER_TOPIC = int(CONFIG.get("MAX_ARTICLES_PER_TOPIC", 1))
DEMOTE_FACTOR = float(CONFIG.get("DEMOTE_FACTOR", 0.5))
MATCH_THRESHOLD = float(CONFIG.get("DEDUPLICATION_MATCH_THRESHOLD", 0.4)) 
GEMINI_MODEL_NAME = CONFIG.get("GEMINI_MODEL_NAME", "gemini-2.5-flash") 
BATCH_SIZE = 10 # Consolidated fetching size

USER_TIMEZONE = CONFIG.get("TIMEZONE", "America/New_York")
try:
    ZONE = ZoneInfo(USER_TIMEZONE)
except Exception:
    ZONE = ZoneInfo("America/New_York")

def load_csv_weights(url):
    weights = {}
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        reader = csv.reader(response.text.splitlines())
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                try: weights[row[0].strip()] = int(row[1])
                except: continue
        return weights
    except Exception as e:
        logging.error(f"Failed to load weights: {e}"); return None
    
def load_overrides(url):
    overrides = {}
    try:
        response = requests.get(url, timeout=15); response.raise_for_status()
        reader = csv.reader(response.text.splitlines()); next(reader, None)
        for row in reader:
            if len(row) >= 2: overrides[row[0].strip().lower()] = row[1].strip().lower()
        return overrides
    except Exception as e:
        logging.error(f"Failed to load overrides: {e}"); return None

TOPIC_WEIGHTS = load_csv_weights(TOPICS_CSV_URL)
KEYWORD_WEIGHTS = load_csv_weights(KEYWORDS_CSV_URL)
OVERRIDES = load_overrides(OVERRIDES_CSV_URL)

if None in (TOPIC_WEIGHTS, KEYWORD_WEIGHTS, OVERRIDES):
    if os.path.exists(LOCKFILE): os.remove(LOCKFILE)
    sys.exit(1)

def normalize(text):
    words = re.findall(r'\b\w+\b', text.lower())
    stemmed = [stemmer.stem(w) for w in words]
    lemmatized = [lemmatizer.lemmatize(w) for w in stemmed]
    return " ".join(lemmatized)

def is_in_history(article_title: str, history: dict, threshold: float) -> bool:
    norm_title_tokens = set(normalize(article_title).split())
    if not norm_title_tokens: return False
    for articles_in_topic in history.values():
        for past_article_data in articles_in_topic:
            past_tokens = set(normalize(past_article_data.get("title", "")).split())
            if not past_tokens: continue
            intersection_len = len(norm_title_tokens.intersection(past_tokens))
            union_len = len(norm_title_tokens.union(past_tokens))
            if union_len == 0: continue
            if (intersection_len / union_len) >= threshold: return True
    return False

def to_user_timezone(dt):
    return dt.astimezone(ZONE)

def fetch_articles_for_batch(topics_batch, max_articles=20):
    """Consolidates requests into batches to avoid 503 errors and speed up processing."""
    query_string = " OR ".join([f'"{t}"' for t in topics_batch])
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(f'({query_string})')}&hl=en-US&gl=US&ceid=US:en"
    
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ]

    for attempt in range(3):
        try:
            headers = {"User-Agent": random.choice(user_agents)}
            response = requests.get(url, headers=headers, timeout=25)
            if response.status_code == 503:
                time.sleep((attempt + 1) * 7); continue
            response.raise_for_status()
            root = ET.fromstring(response.content)
            time_cutoff_utc = datetime.now(ZoneInfo("UTC")) - timedelta(hours=MAX_ARTICLE_HOURS)
            articles = []
            for item in root.findall("./channel/item"):
                title = item.find("title").text.strip()
                link = item.find("link").text
                pubDate_text = item.find("pubDate").text
                try:
                    pub_dt = parsedate_to_datetime(pubDate_text).astimezone(ZoneInfo("UTC"))
                    if pub_dt > time_cutoff_utc: articles.append({"title": title, "link": link, "pubDate": pubDate_text})
                except: continue
            return articles
        except Exception as e:
            if attempt == 2: logging.error(f"Batch fetch failed: {e}")
            time.sleep(2)
    return []

def load_recent_headlines_from_history(history_data: dict, max_headlines: int) -> list:
    if not history_data: return []
    all_articles = []
    for topic_articles in history_data.values(): all_articles.extend(topic_articles)
    def get_date_key(article):
        try: return parsedate_to_datetime(article.get("pubDate", "")).astimezone(ZoneInfo("UTC"))
        except: return datetime.min.replace(tzinfo=ZoneInfo("UTC"))
    all_articles.sort(key=get_date_key, reverse=True)
    return [article['title'] for article in all_articles[:max_headlines]]

def safe_parse_json(raw_json_string: str) -> dict:
    if not raw_json_string: return {}
    text = re.sub(r"^```(?:json)?\s*", "", raw_json_string.strip())
    text = re.sub(r"\s*```$", "", text).strip()
    try: return json.loads(text)
    except:
        text = text.replace("“", '"').replace("”", '"').replace("True", "true").replace("False", "false")
        try: return ast.literal_eval(text) if isinstance(ast.literal_eval(text), dict) else {}
        except: return {}

def contains_banned_keyword(text, banned_terms):
    if not text: return False
    norm_text = normalize(text)
    return any(banned_term in norm_text for banned_term in banned_terms if banned_term)

# --- Tool Definition ---
digest_tool_schema = {
    "type": "object",
    "properties": {
        "selected_digest_entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic_name": {"type": "string"},
                    "headlines": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["topic_name", "headlines"]
            }
        }
    },
    "required": ["selected_digest_entries"]
}

SELECT_DIGEST_ARTICLES_TOOL = Tool(
    function_declarations=[FunctionDeclaration(name="format_digest_selection", description="Curate selection.", parameters=digest_tool_schema)]
)

def prioritize_with_gemini(headlines_to_send: dict, digest_history: list, gemini_api_key: str, topic_weights: dict, keyword_weights: dict, overrides: dict) -> dict:
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel(model_name=GEMINI_MODEL_NAME, tools=[SELECT_DIGEST_ARTICLES_TOOL])
    pref_data = {"topic_weights": topic_weights, "keyword_weights": keyword_weights, "banned_terms": [k for k, v in overrides.items() if v == "ban"], "demoted_terms": [k for k, v in overrides.items() if v == "demote"]}

    prompt = (
        "You are an Advanced News Synthesis Engine. Your function is to act as an expert, hyper-critical news curator. Your single most important mission is to produce a high-signal, non-redundant, and deeply relevant news digest for a user. You must be ruthless in eliminating noise, repetition, and low-quality content.\n\n"
        f"### Inputs Provided\n1.  **User Preferences:**\n```json\n{json.dumps(pref_data, indent=2)}\n```\n"
        f"2.  **Candidate Headlines:**\n```json\n{json.dumps(dict(sorted(headlines_to_send.items())), indent=2)}\n```\n"
        f"3.  **Digest History:**\n```json\n{json.dumps(digest_history, indent=2)}\n```\n\n"
        "### Core Processing Pipeline (Follow these steps sequentially)\n\n"
        "**Step 1: Cross-Topic Semantic Clustering & Deduplication (CRITICAL FIRST STEP)**\nFirst, analyze ALL `Candidate Headlines`. identify and group all headlines from ALL topics that cover the same core news event.\n"
        "**Step 2: History-Based Filtering**\nCompare champion against `Digest History`. If idential event, DISCARD.\n"
        "**Step 3: Rigorous Relevance & Quality Filtering**\n"
        f"*   **Output Limits:** Strictly {MAX_TOPICS} topics and {MAX_ARTICLES_PER_TOPIC} headlines per topic.\n"
        "*   **Content Quality & Style (CRITICAL):** REJECT Sensationalist, Clickbait, Fluff, or biased Op-eds.\n"
        "**Step 4: Final Selection and Ordering**\nOrder topics and headlines from most to least significant.\n\n"
        "### Final Output\nUse the 'format_digest_selection' tool."
    )

    for attempt in range(3):
        try:
            response = model.generate_content([prompt], tool_config={"function_calling_config": {"mode": "ANY", "allowed_function_names": ["format_digest_selection"]}})
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        args = part.function_call.args
                        transformed = {}
                        entries = args.get("selected_digest_entries", [])
                        for entry in entries: transformed[entry.get("topic_name").strip()] = list(entry.get("headlines", []))
                        return transformed
            return {}
        except Exception as e:
            if "503" in str(e) and attempt < 2:
                logging.warning("Gemini busy. Retrying in 10s..."); time.sleep(10); continue
            logging.error(f"Gemini error: {e}"); return {}
    return {}
    
def git_push_history_json(history_file_path, base_dir, zone_for_commit_msg):
    try:
        github_user, github_token, github_repository = os.getenv("GITHUB_USER"), os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
        if not all([github_user, github_token, github_repository]): return
        subprocess.run(["git", "-C", base_dir, "add", os.path.relpath(history_file_path, base_dir)])
        subprocess.run(["git", "-C", base_dir, "commit", "-m", f"Automated history update {datetime.now(zone_for_commit_msg)}"])
        remote_url = f"https://{github_user}:{github_token}@github.com/{github_repository}.git"
        subprocess.run(["git", "-C", base_dir, "push", remote_url, "HEAD"])
    except Exception as e: logging.error(f"Git push failed: {e}")

def main():
    history = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f: history = json.load(f)
        except: history = {}

    MAX_HISTORY_HEADLINES_FOR_LLM = int(CONFIG.get("MAX_HISTORY_HEADLINES_FOR_LLM", 150))
    recent_headlines_for_llm = load_recent_headlines_from_history(history, MAX_HISTORY_HEADLINES_FOR_LLM)

    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        headlines_to_send, full_articles_map = {}, {}
        banned_terms = [k for k, v in OVERRIDES.items() if v == "ban"]
        fetch_limit = int(CONFIG.get("ARTICLES_TO_FETCH_PER_TOPIC", 20))

        # --- BATCHED FETCHING STAGE ---
        topic_keys = list(TOPIC_WEIGHTS.keys())
        random.shuffle(topic_keys)
        batches = [topic_keys[i:i + BATCH_SIZE] for i in range(0, len(topic_keys), BATCH_SIZE)]

        logging.info(f"--- Starting Batched Article Fetching ({len(batches)} batches) ---")

        for batch in batches:
            articles_for_batch = fetch_articles_for_batch(batch, fetch_limit)
            time.sleep(random.uniform(1.5, 3.0)) 

            for article in articles_for_batch:
                title, norm_art_title = article['title'], normalize(article['title'])
                if is_in_history(title, history, MATCH_THRESHOLD) or contains_banned_keyword(title, banned_terms): continue
                
                # Robust Attribution Logic
                best_topic, highest_w = None, -1
                for topic in batch:
                    norm_topic = normalize(topic)
                    if norm_topic in norm_art_title or any(word in norm_art_title for word in norm_topic.split() if len(word) > 3):
                        weight = TOPIC_WEIGHTS.get(topic, 0)
                        if weight > highest_w: highest_w, best_topic = weight, topic
                
                if not best_topic: best_topic = max(batch, key=lambda t: TOPIC_WEIGHTS.get(t, 0))
                
                headlines_to_send.setdefault(best_topic, []).append(title)
                full_articles_map[norm_art_title] = article 

        if not headlines_to_send: return

        selected_digest_content = prioritize_with_gemini(headlines_to_send, recent_headlines_for_llm, gemini_api_key, TOPIC_WEIGHTS, KEYWORD_WEIGHTS, OVERRIDES)
        if not selected_digest_content: return
        
        final_digest_to_email, processed_norm_titles = {}, set()
        for topic, titles_from_gemini in selected_digest_content.items():
            valid_arts = []
            for t in titles_from_gemini[:MAX_ARTICLES_PER_TOPIC]:
                norm_t = normalize(t)
                if norm_t in processed_norm_titles: continue
                data = full_articles_map.get(norm_t)
                if data: valid_arts.append(data); processed_norm_titles.add(norm_t)
                else:
                    for stored_norm, stored_data in full_articles_map.items():
                        if norm_t in stored_norm and stored_norm not in processed_norm_titles:
                            valid_arts.append(stored_data); processed_norm_titles.add(stored_norm); break
            if valid_arts: final_digest_to_email[topic] = valid_arts

        if not final_digest_to_email: return

        # --- Email Sending ---
        EMAIL_FROM = os.getenv("GMAIL_USER")
        EMAIL_PASS, EMAIL_BCC = os.getenv("GMAIL_APP_PASSWORD"), [e.strip() for e in os.getenv("MAILTO", "").split(",") if e.strip()]
        
        html_body_parts = ["<h2>Your News Digest</h2>"]
        for topic, articles in final_digest_to_email.items():
            section = f'<h3>{html.escape(topic)}</h3>'
            for art in articles:
                date_str = to_user_timezone(parsedate_to_datetime(art["pubDate"])).strftime("%a, %d %b %Y %I:%M %p")
                section += f'<p>📰 <a href="{art["link"]}">{html.escape(art["title"])}</a><br><small>{date_str}</small></p>'
            html_body_parts.append(section)
        
        msg = EmailMessage()
        msg["Subject"] = f"🗞️ News Digest – {datetime.now(ZONE).strftime('%Y-%m-%d %I:%M %p')}"
        msg["From"], msg["To"], msg["Bcc"] = EMAIL_FROM, EMAIL_FROM, ", ".join(EMAIL_BCC)
        msg.add_alternative(f"<html><body>{''.join(html_body_parts)}</body></html>", subtype="html")

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls(); server.login(EMAIL_FROM, EMAIL_PASS); server.send_message(msg)
        
        for topic, articles_sent in final_digest_to_email.items():
            history.setdefault(topic, []).extend([{"title": a["title"], "pubDate": a["pubDate"]} for a in articles_sent])
            history[topic] = history[topic][-40:]

        with open(HISTORY_FILE, "w", encoding="utf-8") as f: json.dump(history, f, indent=2)
        if CONFIG.get("ENABLE_GIT_PUSH", False): git_push_history_json(HISTORY_FILE, BASE_DIR, ZONE)

    except Exception as e: logging.critical(f"Main Error: {e}", exc_info=True)
    finally:
        if os.path.exists(LOCKFILE): os.remove(LOCKFILE)
        logging.info(f"Script finished at {datetime.now(ZONE)}")
             
if __name__ == "__main__":
    main()