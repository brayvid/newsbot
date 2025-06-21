# Author: Blake Rayvid <https://github.com/brayvid/newsbot>

import os
import sys
import subprocess # Added for git operations

# Set number of threads for various libraries to 1 if parallelism is not permitted on your system
# os.environ["OPENBLAS_NUM_THREADS"] = "1"
# os.environ["OMP_NUM_THREADS"] = "1"
# os.environ["MKL_NUM_THREADS"] = "1"
# os.environ["NUMEXPR_NUM_THREADS"] = "1"

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
import shutil
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
nltk.data.path.append(os.path.join(BASE_DIR, "nltk_data"))

def ensure_nltk_data():
    nltk_data_dir = os.path.join(BASE_DIR, "nltk_data")
    os.makedirs(nltk_data_dir, exist_ok=True)
    for resource in ['wordnet', 'omw-1.4']:
        try: 
            find(f'corpora/{resource}')
        except LookupError:
            try:
                logging.info(f"Downloading NLTK resource: {resource} to {nltk_data_dir}")
                nltk.download(resource, download_dir=nltk_data_dir)
            except Exception as e:
                print(f"Failed to download {resource}: {e}")
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
                    if '.' in val:
                        config[key] = float(val)
                    else:
                        config[key] = int(val)
                except ValueError:
                    config[key] = val  # fallback to string
        return config
    except Exception as e:
        logging.error(f"Failed to load config from {url}: {e}")
        return None

# Load config before main
CONFIG = load_config_from_sheet(CONFIG_CSV_URL)
if CONFIG is None:
    logging.critical("Fatal: Unable to load CONFIG from sheet. Exiting.")
    if os.path.exists(LOCKFILE):
        os.remove(LOCKFILE)
    sys.exit(1)

MAX_ARTICLE_HOURS = int(CONFIG.get("MAX_ARTICLE_HOURS", 6))
MAX_TOPICS = int(CONFIG.get("MAX_TOPICS", 7))
MAX_ARTICLES_PER_TOPIC = int(CONFIG.get("MAX_ARTICLES_PER_TOPIC", 1))
DEMOTE_FACTOR = float(CONFIG.get("DEMOTE_FACTOR", 0.5))
MATCH_THRESHOLD = 0.4

USER_TIMEZONE = CONFIG.get("TIMEZONE", "America/New_York")
try:
    ZONE = ZoneInfo(USER_TIMEZONE)
except Exception:
    logging.warning(f"Invalid TIMEZONE '{USER_TIMEZONE}' in config. Falling back to 'America/New_York'")
    ZONE = ZoneInfo("America/New_York")

def load_csv_weights(url):
    weights = {}
    try:
        response = requests.get(url, timeout=15)
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
        return weights
    except Exception as e:
        logging.error(f"Failed to load weights from {url}: {e}")
        return None
    
def load_overrides(url):
    overrides = {}
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        reader = csv.reader(response.text.splitlines())
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                overrides[row[0].strip().lower()] = row[1].strip().lower()
        return overrides
    except Exception as e:
        logging.error(f"Failed to load overrides: {e}")
        return None

TOPIC_WEIGHTS = load_csv_weights(TOPICS_CSV_URL)
KEYWORD_WEIGHTS = load_csv_weights(KEYWORDS_CSV_URL)
OVERRIDES = load_overrides(OVERRIDES_CSV_URL)

if None in (TOPIC_WEIGHTS, KEYWORD_WEIGHTS, OVERRIDES):
    logging.critical("Fatal: Failed to load topics, keywords, or overrides. Exiting.")
    if os.path.exists(LOCKFILE):
        os.remove(LOCKFILE)
    sys.exit(1)

def normalize(text):
    words = text.lower().split()
    stemmed = [stemmer.stem(w) for w in words]
    lemmatized = [lemmatizer.lemmatize(w) for w in stemmed]
    return " ".join(lemmatized)

def is_in_history(article_title, history):
    norm_title_tokens = set(normalize(article_title).split())
    if not norm_title_tokens:
        return False

    for articles_in_topic in history.values():
        for a in articles_in_topic:
            past_tokens = set(normalize(a["title"]).split())
            if not past_tokens:
                continue
            
            intersection_len = len(norm_title_tokens.intersection(past_tokens))
            union_len = len(norm_title_tokens.union(past_tokens))
            if union_len == 0:
                similarity = 1.0 if not norm_title_tokens else 0.0
            else:
                similarity = intersection_len / union_len

            if similarity >= MATCH_THRESHOLD:
                return True
    return False

def to_user_timezone(dt):
    return dt.astimezone(ZONE)

def fetch_articles_for_topic(topic, max_articles=10):
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(topic)}&hl=en-US&gl=US&ceid=US:en"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 NewsBot/1.0"}
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        time_cutoff = datetime.now(ZONE) - timedelta(hours=MAX_ARTICLE_HOURS)
        articles = []

        for item in root.findall("./channel/item"):
            title_element = item.find("title")
            title = title_element.text if title_element is not None else "No title"
            
            link_element = item.find("link")
            link = link_element.text if link_element is not None else None

            pubDate_element = item.find("pubDate")
            pubDate_text = pubDate_element.text if pubDate_element is not None else None

            if not title or not link or not pubDate_text:
                logging.warning(f"Skipping article with missing title, link, or pubDate for topic {topic}")
                continue

            try:
                pub_dt_naive = parsedate_to_datetime(pubDate_text)
                if pub_dt_naive.tzinfo is None:
                    pub_dt_utc = pub_dt_naive.replace(tzinfo=ZoneInfo("UTC"))
                else:
                    pub_dt_utc = pub_dt_naive.astimezone(ZoneInfo("UTC"))
                pub_dt_user_tz = pub_dt_utc.astimezone(ZONE)

            except Exception as e:
                logging.warning(f"Malformed pubDate '{pubDate_text}' for article '{title}': {e}. Skipping.")
                continue 

            if pub_dt_user_tz <= time_cutoff:
                continue

            articles.append({
                "title": title,
                "link": link,
                "pubDate": pubDate_text
            })

            if len(articles) >= max_articles:
                break 
        return articles
    except requests.exceptions.Timeout:
        logging.warning(f"Timeout fetching articles for {topic} from {url}")
        return []
    except requests.exceptions.RequestException as e:
        logging.warning(f"Failed to fetch articles for {topic} from {url}: {e}")
        return []
    except ET.ParseError as e:
        logging.warning(f"Failed to parse XML for {topic} from {url}: {e}")
        return []

def build_user_preferences(topics, keywords, overrides):
    preferences = []
    if topics:
        preferences.append("User topics (ranked 1-5 in importance):")
        for topic, score in sorted(topics.items(), key=lambda x: -x[1]):
            preferences.append(f"- {topic}: {score}")
    if keywords:
        preferences.append("\nHeadline keywords (ranked 1-5 in importance):")
        for keyword, score in sorted(keywords.items(), key=lambda x: -x[1]):
            preferences.append(f"- {keyword}: {score}")
    banned = sorted([k for k, v in overrides.items() if v == "ban"])
    demoted = sorted([k for k, v in overrides.items() if v == "demote"])
    if banned:
        preferences.append("\nBanned terms (must not appear in topics or headlines):")
        for term in banned:
            preferences.append(f"- {term}")
    if demoted:
        preferences.append(f"\nDemoted terms (consider headlines with these terms {DEMOTE_FACTOR} times as important to the user, all else equal):")
        for term in demoted:
            preferences.append(f"- {term}")
    return "\n".join(preferences)

def safe_parse_json(raw: str) -> dict:
    if not raw:
        logging.warning("safe_parse_json received empty input.")
        return {}
    text_to_parse = raw.strip()
    if text_to_parse.startswith("```"):
        text_to_parse = re.sub(r"^```(?:json)?\s*", "", text_to_parse)
        text_to_parse = re.sub(r"\s*```$", "", text_to_parse)
        text_to_parse = text_to_parse.strip()
    try:
        return json.loads(text_to_parse)
    except json.JSONDecodeError as e_json:
        logging.warning(f"Initial JSON parsing failed: {e_json}. Attempting ast.literal_eval.")
        try:
            py_compat_text = text_to_parse.replace(': true', ': True').replace(': false', ': False').replace(': null', ': None')
            return ast.literal_eval(py_compat_text)
        except (ValueError, SyntaxError) as e_ast:
            logging.error(f"ast.literal_eval also failed: {e_ast}. JSON content was:\n{raw[:1000]}")
            return {}

def contains_banned_keyword(text, banned_terms):
    norm_text = normalize(text)
    return any(normalize(banned_term) in norm_text for banned_term in banned_terms)

def prioritize_with_gemini(headlines_to_send: dict, user_preferences: str, gemini_api_key: str) -> dict:
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash-latest",
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json"
        )
    )
    prompt = (
        "You are an expert news curator. Your task is to select the most relevant news topics and headlines for a user's email digest based on their explicit preferences. "
        "The user has provided a list of topics they are interested in, keywords they look for in headlines, and terms that should be banned or demoted. "
        "Each preference has an importance score (1-5, 5 being most important).\n"
        f"Constraints:\n"
        f"- Select up to {MAX_TOPICS} topics for the digest.\n"
        f"- For each selected topic, choose up to {MAX_ARTICLES_PER_TOPIC} headline(s).\n"
        "- Strictly adhere to banned terms: headlines containing banned terms must be excluded.\n"
        f"- Apply demotion: headlines with demoted terms should be considered {DEMOTE_FACTOR} times less important.\n"
        "- Deduplication: Avoid multiple headlines covering the exact same event, even if phrased differently or in different topics. Pick the best one.\n"
        "- Content Quality: Prioritize informative, content-rich headlines. Avoid clickbait, questions, listicles, or overly sensationalized titles.\n"
        "- Focus: Prefer U.S. national news or significant international news. Avoid hyper-local news (e.g., specific small towns, local counties) unless it has broader implications.\n"
        "- Diversity: Aim for a reasonable diversity of subjects across the selected topics. Do not let one single theme dominate if other relevant news is available.\n"
        "- Ads/Products: Reject advertisements and mentions of specific products/services unless the mention itself is newsworthy (e.g., major product recall, significant tech innovation discussion).\n\n"
        "Input:\n"
        "1. User Preferences:\n"
        f"{user_preferences}\n\n"
        "2. Available Headlines (categorized by the topic they were fetched for):\n"
        f"{json.dumps(dict(sorted(headlines_to_send.items())), indent=2)}\n\n"
        "Output Format:\n"
        "Respond ONLY with a valid JSON object. The JSON should be a dictionary where keys are topic names (strings) and values are lists of selected headline strings for that topic. Example:\n"
        "{ \"Technology\": [\"Major Tech Company Announces Breakthrough AI\", \"New Cybersecurity Threat Emerges\"], \"World News\": [\"Global Summit Addresses Climate Change\"] }\n"
        "If no suitable headlines are found for a topic, or if a topic is not selected, do not include it in the output JSON.\n"
        "If no headlines meet the criteria at all, return an empty JSON object: {}"
    )
    logging.info("Sending prompt to Gemini for prioritization.")
    try:
        response = model.generate_content([prompt])
        if not response.parts:
            logging.warning("Gemini response has no parts.")
            return {}
        raw_json_text = response.text
        logging.info("Received response from Gemini.")
        parsed_json = safe_parse_json(raw_json_text)
        if not isinstance(parsed_json, dict):
            logging.error(f"Parsed JSON is not a dictionary. Type: {type(parsed_json)}. Content: {str(parsed_json)[:500]}")
            return {}
        return parsed_json
    except Exception as e:
        logging.error(f"Error during Gemini API call or processing response: {e}", exc_info=True)
        return {}

def git_push_history_json(history_file_path, base_dir, zone_for_commit_msg):
    """Adds, commits (if history.json changed and was staged), and pushes to GitHub using .env credentials."""
    try:
        github_user = os.getenv("GITHUB_USER")
        github_token = os.getenv("GITHUB_TOKEN")
        github_email = os.getenv("GITHUB_EMAIL")
        github_repository = os.getenv("GITHUB_REPOSITORY")  # Format: "owner/repo-name"

        if not all([github_user, github_token, github_repository]):
            logging.error("GITHUB_USER, GITHUB_TOKEN, or GITHUB_REPOSITORY not set in .env. Skipping git operations.")
            return

        relative_history_file = os.path.relpath(history_file_path, base_dir)
        if not os.path.exists(history_file_path):
            logging.info(f"{history_file_path} not found. Skipping git operations.")
            return

        logging.info(f"Attempting git operations for {relative_history_file} from {base_dir}")

        # Configure git user for this commit, if email/user are provided
        # This sets the config for the current repository for subsequent git commands.
        if github_email:
            email_config_cmd = ["git", "config", "user.email", github_email]
            subprocess.run(email_config_cmd, cwd=base_dir, check=False, capture_output=True, text=True)
            logging.info(f"Attempted to set git config user.email to {github_email}")

        if github_user: # Using GITHUB_USER as the commit author name.
            name_config_cmd = ["git", "config", "user.name", github_user]
            subprocess.run(name_config_cmd, cwd=base_dir, check=False, capture_output=True, text=True)
            logging.info(f"Attempted to set git config user.name to {github_user}")

        # 1. Git Add the specific history file
        add_cmd = ["git", "add", relative_history_file]
        add_process = subprocess.run(add_cmd, cwd=base_dir, capture_output=True, text=True, check=False)
        if add_process.returncode != 0:
            logging.warning(f"git add {relative_history_file} exited with code {add_process.returncode}: {add_process.stderr.strip()}. Proceeding with commit attempt.")

        # 2. Git Commit
        commit_message = f"Automated: Update {os.path.basename(history_file_path)} {datetime.now(zone_for_commit_msg).strftime('%Y-%m-%d %H:%M:%S %Z')}"
        commit_cmd = ["git", "commit", "-m", commit_message]
        commit_process = subprocess.run(commit_cmd, cwd=base_dir, capture_output=True, text=True, check=False)

        if commit_process.returncode == 0:
            logging.info(f"Commit successful. Message: '{commit_message}'\n{commit_process.stdout.strip()}")
        elif ("nothing to commit" in commit_process.stdout.lower() or 
              "no changes added to commit" in commit_process.stdout.lower() or
              (commit_process.returncode == 1 and not commit_process.stderr.strip() and "nothing to commit" in commit_process.stdout.lower())):
            logging.info(f"No changes to commit for {relative_history_file}. Git output: {commit_process.stdout.strip()}")
            # If nothing was committed, no need to push this specific change.
            # However, other changes might have been staged, so we could still attempt a general push if desired.
            # For now, if this specific commit failed due to no changes, we log and can decide to skip push.
            # Let's assume we still want to try pushing if other things might be ready.
        else:
            logging.error(f"git commit failed with code {commit_process.returncode}. Stderr: {commit_process.stderr.strip()}. Stdout: {commit_process.stdout.strip()}")
            # Even if commit fails, maybe a push of prior commits is desired? Or stop?
            # For now, log error and proceed to push attempt.

        # 3. Git Push
        # Construct the authenticated remote URL
        remote_url = f"https://{github_user}:{github_token}@github.com/{github_repository}.git"

        # Get current branch
        current_branch = ""
        try:
            get_branch_cmd = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
            branch_process = subprocess.run(get_branch_cmd, cwd=base_dir, capture_output=True, text=True, check=True)
            current_branch = branch_process.stdout.strip()
            if not current_branch:
                logging.error("Could not determine current git branch. Skipping git push.")
                return
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to get current git branch: {e.stderr.strip()}. Skipping git push.")
            return
        except FileNotFoundError:
            logging.error("git command not found while trying to get branch. Ensure Git is installed and in PATH.")
            return


        logging.info(f"Attempting git push to repository {github_repository} on branch {current_branch}...")
        # The push command will use the remote_url which includes credentials.
        push_cmd = ["git", "push", remote_url, current_branch]
        push_process = subprocess.run(push_cmd, cwd=base_dir, capture_output=True, text=True, check=False)
        
        if push_process.returncode == 0:
            logging.info(f"git push successful to {github_repository} branch {current_branch}.\n{push_process.stdout.strip()}")
        elif ("everything up-to-date" in push_process.stdout.lower() or
              "everything up-to-date" in push_process.stderr.lower()):
            logging.info(f"git push: Everything up-to-date for {github_repository} branch {current_branch}. Git output: {push_process.stdout.strip()} {push_process.stderr.strip()}")
        else:
            # Mask the token in the log if the command is part of the error.
            # The command itself is not directly logged here, but stderr might echo parts of it.
            # For now, just log the error. More robust masking would involve parsing stderr.
            logging.error(f"git push to {github_repository} branch {current_branch} failed with code {push_process.returncode}. Stderr: {push_process.stderr.strip()}. Stdout: {push_process.stdout.strip()}")

    except FileNotFoundError: 
        logging.error("git command not found. Please ensure Git is installed and in your system's PATH.")
    except Exception as e:
        logging.error(f"An unexpected error occurred during git operations: {e}", exc_info=True)


def main():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        except json.JSONDecodeError:
            logging.warning(f"Could not decode {HISTORY_FILE}. Initializing empty history.")
            history = {}
    else:
        history = {}

    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            logging.error("Missing GEMINI_API_KEY. Exiting.")
            return

        user_preferences = build_user_preferences(TOPIC_WEIGHTS, KEYWORD_WEIGHTS, OVERRIDES)
        headlines_to_send = {}
        full_articles_map = {}
        banned_terms = [k for k, v in OVERRIDES.items() if v == "ban"]

        for topic in TOPIC_WEIGHTS:
            articles_for_this_topic = fetch_articles_for_topic(topic, 20)
            if not articles_for_this_topic:
                continue
            allowed_titles_for_topic = []
            for article in articles_for_this_topic:
                if is_in_history(article["title"], history) or contains_banned_keyword(article["title"], banned_terms):
                    continue
                allowed_titles_for_topic.append(article["title"])
                full_articles_map[normalize(article["title"])] = article
            if allowed_titles_for_topic:
                headlines_to_send[topic] = allowed_titles_for_topic

        if not headlines_to_send:
            logging.info("No fresh, non-banned headlines available after initial filtering. Nothing to send to LLM.")
            return

        total_headlines_candidate_count = sum(len(v) for v in headlines_to_send.values())
        logging.info(f"Sending {total_headlines_candidate_count} candidate headlines across {len(headlines_to_send)} topics to Gemini.")

        selected_digest_content = prioritize_with_gemini(headlines_to_send, user_preferences, gemini_api_key)

        if not selected_digest_content or not isinstance(selected_digest_content, dict):
            logging.info("Gemini returned no valid digest content or content was not a dictionary.")
            return
        
        final_digest_to_email = {}
        processed_normalized_titles = set()

        for topic, titles_from_gemini in selected_digest_content.items():
            if not isinstance(titles_from_gemini, list):
                logging.warning(f"Gemini output for topic '{topic}' is not a list: {titles_from_gemini}. Skipping topic.")
                continue
            articles_for_email_topic = []
            for title in titles_from_gemini:
                if not isinstance(title, str):
                    logging.warning(f"Encountered non-string title in Gemini output for topic '{topic}': {title}. Skipping.")
                    continue
                normalized_title_from_gemini = normalize(title)
                if normalized_title_from_gemini in processed_normalized_titles:
                    logging.info(f"Skipping already processed (duplicate) title '{title}' from Gemini for topic '{topic}'.")
                    continue
                original_article_data = full_articles_map.get(normalized_title_from_gemini)
                if original_article_data:
                    articles_for_email_topic.append(original_article_data)
                    processed_normalized_titles.add(normalized_title_from_gemini)
                else:
                    logging.warning(f"Could not find original article data for title '{title}' (normalized: '{normalized_title_from_gemini}') from Gemini. It might have been rephrased. Skipping.")
            if articles_for_email_topic:
                final_digest_to_email[topic] = articles_for_email_topic

        if not final_digest_to_email:
            logging.info("No articles selected for the final email digest after Gemini processing and deduplication.")
            return

        EMAIL_FROM = os.getenv("GMAIL_USER", "").encode("ascii", "ignore").decode()
        EMAIL_TO = EMAIL_FROM
        EMAIL_BCC = os.getenv("MAILTO", "").strip()
        EMAIL_BCC_LIST = [email.strip() for email in EMAIL_BCC.split(",") if email.strip()]
        
        if not EMAIL_BCC_LIST and not EMAIL_TO:
             logging.error("No recipients configured (GMAIL_USER is empty and MAILTO is empty). Cannot send email.")
             return

        SMTP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
        SMTP_SERVER = "smtp.gmail.com"
        SMTP_PORT = 587

        if not EMAIL_FROM or not SMTP_PASS:
            logging.error("GMAIL_USER or GMAIL_APP_PASSWORD not set. Cannot send email.")
            return

        html_body_parts = ["<h2>Your News Digest</h2>"]
        total_articles_in_digest = 0
        for topic, articles in final_digest_to_email.items():
            section = f'<h3 style="margin-top: 20px; margin-bottom: 5px; border-bottom: 1px solid #eee; padding-bottom: 3px;">{html.escape(topic)}</h3>'
            article_html_parts = []
            for article in articles:
                total_articles_in_digest += 1
                try:
                    pub_dt_obj = parsedate_to_datetime(article["pubDate"])
                    pub_dt_user_tz = to_user_timezone(pub_dt_obj)
                    date_str = pub_dt_user_tz.strftime("%a, %d %b %Y %I:%M %p %Z")
                except Exception:
                    date_str = "Date unavailable"
                article_html_parts.append(
                    f'<p style="margin: 0.4em 0 1.2em 0;">'
                    f'📰 <a href="{html.escape(article["link"])}" target="_blank">{html.escape(article["title"])}</a><br>'
                    f'<span style="font-size: 0.9em; color: #555;">📅 {date_str}</span>'
                    f'</p>'
                )
            section += "".join(article_html_parts)
            html_body_parts.append(section)
        
        html_body = "".join(html_body_parts)
        footer_info = f'{total_articles_in_digest} articles selected by Gemini from {total_headlines_candidate_count} candidates published in the last {MAX_ARTICLE_HOURS} hours, based on your <a href="https://docs.google.com/spreadsheets/d/1OjpsQEnrNwcXEWYuPskGRA5Jf-U8e_x0x3j2CKJualg/edit?usp=sharing" target="_blank">preferences</a>.'
        html_body += f"<hr><p style=\"font-size:0.8em; color:#777;\">{footer_info}</p>"

        msg = EmailMessage()
        current_time_str = datetime.now(ZONE).strftime('%Y-%m-%d %I:%M %p %Z')
        msg["Subject"] = f"🗞️ News Digest – {current_time_str}"
        msg["From"] = EMAIL_FROM
        
        if EMAIL_TO == EMAIL_FROM and EMAIL_FROM: 
            msg["To"] = EMAIL_FROM
        if EMAIL_BCC_LIST:
            msg["Bcc"] = ", ".join(EMAIL_BCC_LIST)
        
        if not msg["To"] and not msg["Bcc"]:
            logging.error("No valid recipients for email (To and Bcc are empty).")
            return

        msg.set_content("This is the plain-text version of your news digest. Please enable HTML to view the formatted version.")
        msg.add_alternative(html_body, subtype="html")

        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_FROM, SMTP_PASS)
                server.send_message(msg)
            logging.info(f"Digest email sent successfully at {current_time_str}.")

            for topic, articles_sent in final_digest_to_email.items():
                topic_key_in_history = topic
                if topic_key_in_history not in history:
                    history[topic_key_in_history] = []
                current_titles_in_history_for_topic = {normalize(a['title']) for a in history[topic_key_in_history]}
                for article_to_add in articles_sent:
                    if normalize(article_to_add['title']) not in current_titles_in_history_for_topic:
                        history[topic_key_in_history].append({
                            "title": article_to_add["title"],
                            "pubDate": article_to_add["pubDate"]
                        })
                history[topic_key_in_history] = history[topic_key_in_history][-40:]
        except smtplib.SMTPAuthenticationError:
            logging.error("SMTP Authentication Error. Check GMAIL_USER and GMAIL_APP_PASSWORD.")
        except Exception as e:
            logging.error(f"Email sending failed: {e}", exc_info=True)

        one_month_ago = datetime.now(ZONE) - timedelta(days=30)
        for topic_key in list(history.keys()):
            pruned_articles_for_topic = []
            for article_entry in history[topic_key]:
                try:
                    pub_dt_naive = parsedate_to_datetime(article_entry["pubDate"])
                    if pub_dt_naive.tzinfo is None:
                         pub_dt_utc = pub_dt_naive.replace(tzinfo=ZoneInfo("UTC"))
                    else:
                        pub_dt_utc = pub_dt_naive.astimezone(ZoneInfo("UTC"))
                    pub_dt_user_tz = pub_dt_utc.astimezone(ZONE)
                    if pub_dt_user_tz >= one_month_ago:
                        pruned_articles_for_topic.append(article_entry)
                except Exception as e:
                    logging.warning(f"Skipping article in history due to malformed pubDate '{article_entry.get('pubDate')}': {e}")
            if pruned_articles_for_topic:
                history[topic_key] = pruned_articles_for_topic
            else:
                del history[topic_key]

        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
        logging.info(f"History saved to {HISTORY_FILE}")

        git_push_history_json(HISTORY_FILE, BASE_DIR, ZONE)

    except Exception as e:
        logging.critical(f"An unhandled error occurred in main: {e}", exc_info=True)
    finally:
        nltk_path_local = os.path.join(BASE_DIR, "nltk_data")
        # if os.path.exists(nltk_path_local): # Decided to keep nltk_data locally
        #     try:
        #         shutil.rmtree(nltk_path_local)
        #         logging.info(f"Cleaned up local nltk_data directory: {nltk_path_local}")
        #     except Exception as e:
        #         logging.warning(f"Failed to delete local nltk_data directory {nltk_path_local}: {e}")

        if os.path.exists(LOCKFILE):
            os.remove(LOCKFILE)
        logging.info(f"Lockfile released. Script finished at {datetime.now(ZONE).strftime('%Y-%m-%d %H:%M:%S %Z')}")

if __name__ == "__main__":
    main()