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
import shutil # Keep for potential future use, though nltk_data cleanup is commented out
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
    # Adjusted to use a user-level directory, common for nltk
    # Or keep it relative to BASE_DIR if preferred for portability/CI
    nltk_home_dir = os.path.expanduser("~/nltk_data")
    download_target_dir = nltk_home_dir # Default to local project path
    
    # Ensure NLTK knows about this path
    # Check if path is already there to avoid duplicates
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
                logging.info(f"Successfully downloaded NLTK resource '{resource}'.")
            except Exception as e:
                print(f"Failed to download {resource}: {e}")
                logging.error(f"Failed to download NLTK resource {resource} to {download_target_dir}: {e}")

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
                        if float(val) == int(float(val)): # Handles "7.0" as int 7
                            config[key] = int(float(val))
                        else:
                            config[key] = float(val)
                    else:
                        config[key] = int(val)
                except ValueError:
                    if val.lower() == 'true':
                        config[key] = True
                    elif val.lower() == 'false':
                        config[key] = False
                    else:
                        config[key] = val
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
MATCH_THRESHOLD = float(CONFIG.get("DEDUPLICATION_MATCH_THRESHOLD", 0.4)) # Added from first script for consistency
GEMINI_MODEL_NAME = CONFIG.get("GEMINI_MODEL_NAME", "gemini-1.5-flash") # Added

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
                    logging.warning(f"Skipping invalid weight in {url}: {row}")
                    continue # Skip malformed rows
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
        logging.error(f"Failed to load overrides from {url}: {e}") # Corrected log message
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
    words = re.findall(r'\b\w+\b', text.lower()) # Use regex to better handle words
    stemmed = [stemmer.stem(w) for w in words]
    lemmatized = [lemmatizer.lemmatize(w) for w in stemmed]
    return " ".join(lemmatized)

def is_in_history(article_title: str, history: dict, threshold: float) -> bool:
    """
    Checks if a given article title is a high-confidence duplicate of any article
    title already in the history log, based on the provided word overlap threshold.
    """
    norm_title_tokens = set(normalize(article_title).split())
    if not norm_title_tokens:
        return False

    for articles_in_topic in history.values():
        for past_article_data in articles_in_topic:
            past_title = past_article_data.get("title", "")
            past_tokens = set(normalize(past_title).split())
            if not past_tokens:
                continue
            
            intersection_len = len(norm_title_tokens.intersection(past_tokens))
            union_len = len(norm_title_tokens.union(past_tokens))
            if union_len == 0: continue

            similarity = intersection_len / union_len
            if similarity >= threshold:
                logging.debug(f"Article '{article_title}' matched past article '{past_title}' with similarity {similarity:.2f} >= {threshold}")
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
        # Compare with MAX_ARTICLE_HOURS from config
        time_cutoff_utc = datetime.now(ZoneInfo("UTC")) - timedelta(hours=MAX_ARTICLE_HOURS)
        articles = []

        for item in root.findall("./channel/item"):
            title_element = item.find("title")
            title = title_element.text if title_element is not None and title_element.text else "No title"
            
            link_element = item.find("link")
            link = link_element.text if link_element is not None and link_element.text else None

            pubDate_element = item.find("pubDate")
            pubDate_text = pubDate_element.text if pubDate_element is not None and pubDate_element.text else None

            if not link or not pubDate_text: # Title can be "No title" but link and pubDate are essential
                logging.warning(f"Skipping article with missing link or pubDate for topic '{topic}': Title '{title}'")
                continue

            try:
                pub_dt_naive = parsedate_to_datetime(pubDate_text)
                if pub_dt_naive.tzinfo is None:
                    pub_dt_utc = pub_dt_naive.replace(tzinfo=ZoneInfo("UTC"))
                else:
                    pub_dt_utc = pub_dt_naive.astimezone(ZoneInfo("UTC"))
            except Exception as e:
                logging.warning(f"Malformed pubDate '{pubDate_text}' for article '{title}': {e}. Skipping.")
                continue 

            if pub_dt_utc <= time_cutoff_utc: # Compare against UTC cutoff
                continue

            articles.append({
                "title": title.strip(), # Ensure title is stripped
                "link": link,
                "pubDate": pubDate_text # Store original pubDate string
            })

            if len(articles) >= max_articles:
                break 
        logging.info(f"Fetched {len(articles)} articles for topic '{topic}'")
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
    except Exception as e: # Catch-all for other unexpected errors
        logging.error(f"Unexpected error fetching articles for {topic} from {url}: {e}")
        return []

def load_recent_headlines_from_history(history_data: dict, max_headlines: int) -> list:
    """
    Extracts a flat list of the most recent headlines from the history.json data.
    This provides the LLM with a representation of what was recently sent.
    """
    if not history_data:
        return []

    all_articles = []
    for topic_articles in history_data.values():
        all_articles.extend(topic_articles)

    # Define a safe key for sorting that handles potential malformed dates
    def get_date_key(article):
        try:
            dt = parsedate_to_datetime(article.get("pubDate", ""))
            # Ensure timezone awareness for correct comparison
            if dt.tzinfo is None:
                return dt.replace(tzinfo=ZoneInfo("UTC"))
            return dt
        except (TypeError, ValueError):
            # Return a very old date for articles with missing/bad dates so they sort last
            return datetime.min.replace(tzinfo=ZoneInfo("UTC"))

    # Sort all articles by publication date, newest first
    all_articles.sort(key=get_date_key, reverse=True)

    # Extract just the titles and limit to the max count
    recent_titles = [article['title'] for article in all_articles[:max_headlines]]
    logging.info(f"Loaded {len(recent_titles)} most recent headlines from history log for LLM context.")
    return recent_titles

def build_user_preferences(topics, keywords, overrides):
    preferences = []
    if topics:
        preferences.append("User topics (ranked 1-5 in importance, 5 is most important):") # Updated text for consistency
        for topic_name, score in sorted(topics.items(), key=lambda x: -x[1]): # Changed var name
            preferences.append(f"- {topic_name}: {score}")
    if keywords:
        preferences.append("\nHeadline keywords (ranked 1-5 in importance, 5 is most important):") # Updated text
        for keyword, score in sorted(keywords.items(), key=lambda x: -x[1]):
            preferences.append(f"- {keyword}: {score}")
    banned = sorted([k for k, v in overrides.items() if v == "ban"])
    demoted = sorted([k for k, v in overrides.items() if v == "demote"])
    if banned:
        preferences.append("\nBanned terms (must not appear in topics or headlines):")
        for term in banned:
            preferences.append(f"- {term}")
    if demoted:
        # This text uses DEMOTE_FACTOR from config. The main prompt for Gemini has a hardcoded "0.1" value.
        # This minor discrepancy is noted. The user requested the main prompt "exactly as is".
        preferences.append(f"\nDemoted terms (consider headlines with these terms {DEMOTE_FACTOR} times less important to the user, all else equal):")
        for term in demoted:
            preferences.append(f"- {term}")
    return "\n".join(preferences)

# Replaced with the more robust version from the first script
def safe_parse_json(raw_json_string: str) -> dict:
    if not raw_json_string:
        logging.warning("safe_parse_json received empty string.")
        return {}
    text = raw_json_string.strip()
    # Remove markdown code block fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    if not text:
        logging.warning("JSON string is empty after stripping wrappers.")
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logging.warning(f"Initial JSON.loads failed: {e}. Attempting cleaning.")
        # Common fixes: Word-style quotes, trailing commas, Python bool/None
        text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
        text = re.sub(r",\s*([\]}])", r"\1", text) # Remove trailing commas before close bracket/brace
        text = text.replace("True", "true").replace("False", "false").replace("None", "null")
        try:
            # Try ast.literal_eval for Python-like dicts if json.loads still fails
            parsed_data = ast.literal_eval(text)
            if isinstance(parsed_data, dict):
                return parsed_data
            else: 
                logging.warning(f"ast.literal_eval parsed to non-dict type: {type(parsed_data)}. Raw: {text[:100]}")
                return {}
        except (ValueError, SyntaxError, TypeError) as e_ast:
            logging.warning(f"ast.literal_eval also failed: {e_ast}. Trying regex for quotes.")
            try:
                # Add quotes around keys
                text = re.sub(r'(?<=([{,]\s*))([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\2":', text)
                # Convert single-quoted string values to double-quoted
                text = re.sub(r":\s*'([^']*)'", r': "\1"', text)
                return json.loads(text)
            except json.JSONDecodeError as e2:
                logging.error(f"JSON.loads failed after all cleaning attempts: {e2}. Raw content (first 500 chars): {raw_json_string[:500]}")
                return {}

def contains_banned_keyword(text, banned_terms):
    if not text: return False # Added to handle empty text
    norm_text = normalize(text)
    # Ensure banned_terms are normalized if they aren't already (assuming they are from OVERRIDES, which are lowercased)
    return any(banned_term in norm_text for banned_term in banned_terms if banned_term) # Added if banned_term

# --- Tool Definition ---
digest_tool_schema = {
    "type": "object",
    "properties": {
        "selected_digest_entries": {
            "type": "array",
            "description": (
                f"A list of selected news topics. Each entry in the list should be an object "
                f"containing a 'topic_name' (string) and 'headlines' (a list of strings). "
                f"Select up to {MAX_TOPICS} topics, and for each topic, select up to "
                f"{MAX_ARTICLES_PER_TOPIC} of the most relevant headlines. Topics and headlines MUST be ordered by significance."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "topic_name": {
                        "type": "string",
                        "description": "The name of the news topic (e.g., 'Technology', 'Climate Change')."
                    },
                    "headlines": {
                        "type": "array",
                        "items": {"type": "string", "description": "A selected headline string for this topic."},
                        "description": f"A list of up to {MAX_ARTICLES_PER_TOPIC} most important headline strings for this topic, ordered by significance."
                    }
                },
                "required": ["topic_name", "headlines"]
            }
        }
    },
    "required": ["selected_digest_entries"]
}

SELECT_DIGEST_ARTICLES_TOOL = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="format_digest_selection",
            description=(
                f"Formats the selected news topics and headlines for the user's digest. "
                f"You MUST select up to {MAX_TOPICS} of the most important topics. "
                f"For each selected topic, return up to {MAX_ARTICLES_PER_TOPIC} most important headlines. "
                "Topics MUST be ordered from most to least significant. Headlines within each topic MUST also be ordered from most to least significant. "
                "The output should be structured as a list of objects, where each object contains a 'topic_name' "
                "and a list of 'headlines' corresponding to that topic."
            ),
            parameters=digest_tool_schema,
        )
    ]
)
# --- End Tool Definition ---

def prioritize_with_gemini(
    headlines_to_send: dict,
    digest_history: list,
    gemini_api_key: str,
    topic_weights: dict,
    keyword_weights: dict,
    overrides: dict
) -> dict:
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL_NAME,
        tools=[SELECT_DIGEST_ARTICLES_TOOL]
    )

    digest_history_json = json.dumps(digest_history, indent=2)

    # Build the preferences JSON from the arguments passed into the function.
    # This makes the function self-contained and removes global dependencies.
    pref_data = {
        "topic_weights": topic_weights,
        "keyword_weights": keyword_weights,
        "banned_terms": [k for k, v in overrides.items() if v == "ban"],
        "demoted_terms": [k for k, v in overrides.items() if v == "demote"]
    }
    user_preferences_json = json.dumps(pref_data, indent=2)

    # The prompt is now fully self-contained and uses the data passed in.
    prompt = (
        "You are an Advanced News Synthesis Engine. Your function is to act as an expert, hyper-critical news curator. Your single most important mission is to produce a high-signal, non-redundant, and deeply relevant news digest for a user. You must be ruthless in eliminating noise, repetition, and low-quality content.\n\n"
        "### Inputs Provided\n"
        f"1.  **User Preferences:** A JSON object defining topic interests, importance weights (1-5), and banned/demoted keywords.\n```json\n{user_preferences_json}\n```\n"
        f"2.  **Candidate Headlines:** A pool of new articles available for today's digest, organized by their machine-assigned topic.\n```json\n{json.dumps(dict(sorted(headlines_to_send.items())), indent=2)}\n```\n"
        f"3.  **Digest History:** A list of headlines the user has already seen in recent digests. You MUST NOT select headlines that are substantively identical to these.\n```json\n{digest_history_json}\n```\n\n"
        "### Core Processing Pipeline (Follow these steps sequentially)\n\n"
        "**Step 1: Cross-Topic Semantic Clustering & Deduplication (CRITICAL FIRST STEP)**\n"
        "First, analyze ALL `Candidate Headlines`. Your primary task is to identify and group all headlines from ALL topics that cover the same core news event. An 'event' is the underlying real-world occurrence, not the specific wording of a headline.\n"
        "-   **Group by Meaning:** Cluster headlines based on their substantive meaning. For example, 'Fed Pauses Rate Hikes,' 'Federal Reserve Holds Interest Rates Steady,' and 'Powell Announces No Change to Fed Funds Rate' all belong to the same cluster.\n"
        "-   **Select One Champion:** From each cluster, select ONLY ONE headline—the one that is the most comprehensive, recent, objective, and authoritative. Discard all other headlines in that cluster immediately.\n\n"
        "**Step 2: History-Based Filtering**\n"
        "Now, take your deduplicated list of 'champion' headlines. Compare each one against the `Digest History`. If any of your champion headlines reports on the exact same event that has already been sent, DISCARD it. Only select news that provides a significant, new update.\n\n"
        "**Step 3: Rigorous Relevance & Quality Filtering**\n"
        "For the remaining, unique, and new headlines, apply the following strict filtering criteria with full force:\n\n"
        f"*   **Output Limits:** Adhere strictly to a maximum of **{MAX_TOPICS} topics** and **{MAX_ARTICLES_PER_TOPIC} headlines** per topic.\n"
        "*   **Geographic Focus:**\n"
        "    - Focus on national (U.S.) or major international news.\n"
        "    - AVOID news that is *solely* of local interest (e.g., specific to a small town) *unless* it has clear and direct national or major international implications relevant to a U.S. audience.\n"
        "*   **Banned/Demoted Content:**\n"
        "    - Strictly REJECT any headlines containing terms flagged as 'banned' in user preferences.\n"
        "    - Headlines with 'demote' terms should be *strongly deprioritized* (effectively treated as having an importance score of 0.1 on a 1-5 scale) and only selected if their relevance is exceptionally high.\n"
        "*   **Commercial Content (APPLY WITH EXTREME PREJUDICE):**\n"
        "    - REJECT advertisements, sponsored content, and articles that are primarily promotional.\n"
        "    - REJECT mentions of specific products/services UNLESS it's highly newsworthy criticism, a major market-moving announcement (e.g., a massive product recall by a major company), or a significant technological breakthrough discussed in a news context, not a promotional one.\n"
        "    - STRICTLY REJECT articles that primarily offer investment advice, promote specific stocks/cryptocurrencies as 'buy now' opportunities, or resemble 'hot stock tips' (e.g., \"Top X Stocks to Invest In,\" \"This Coin Will Explode,\" \"X Stocks Worth Buying\"). News about broad market trends (e.g., \"S&P 500 reaches record high\"), factual company earnings reports (without buy/sell advice), or major regulatory changes IS acceptable. The key is to distinguish objective financial news from investment solicitation.\n"
        "*   **Content Quality & Style (CRITICAL):**\n"
        "    - Ensure a healthy diversity of subjects if possible; do not let one single event dominate the entire digest.\n"
        "    - PRIORITIZE content-rich, factual, objective, and neutrally-toned reporting.\n"
        "    - AGGRESSIVELY AVOID AND REJECT headlines that are:\n"
        "        - Sensationalist, using hyperbole, excessive superlatives (e.g., \"terrifying,\" \"decimated,\" \"gross failure\"), or fear-mongering.\n"
        "        - Purely for entertainment, celebrity gossip, or \"fluff\" pieces lacking substantial news value.\n"
        "        - Clickbait (e.g., withholding key information, using vague teasers like \"You won't believe what happened next!\").\n"
        "        - Primarily opinion/op-ed pieces, especially those with inflammatory or biased language. Focus on reported news.\n"
        "        - Phrased as questions (e.g., \"Is X the new Y?\") or promoting listicles (e.g., \"5 reasons why...\").\n\n"
        "**Step 4: Final Selection and Ordering**\n"
        "From the fully filtered and vetted pool of headlines, make your final selection.\n"
        "1.  **Topic Ordering:** Order the selected topics from most to least significant. Significance is a blend of the user's preference weight and the objective importance of the news you've selected for that topic.\n"
        "2.  **Headline Ordering:** Within each topic, order the selected headlines from most to least newsworthy/comprehensive.\n\n"
        "### Final Output\n"
        "Before calling the tool, perform a final mental check. Ask yourself:\n"
        "- \"Is this headline truly distinct from everything else, including the history?\"\n"
        "- \"Is this trying to sell me a stock, a product, or is it just reporting market news?\"\n"
        "- \"Is this headline objective, or is it heavily opinionated/sensationalist clickbait?\"\n"
        "- \"Is my final topic and headline ordering logical and based on true significance?\"\n\n"
        "Based on this rigorous process, provide your final, curated selection using the 'format_digest_selection' tool."
    )

    logging.info("Sending request to Gemini for prioritization with history.")
    
    try:
        response = model.generate_content(
            [prompt],
            tool_config={"function_calling_config": {"mode": "ANY", "allowed_function_names": ["format_digest_selection"]}}
        )

        finish_reason_display_str = "N/A"
        raw_finish_reason_value = None

        if response.candidates and hasattr(response.candidates[0], 'finish_reason'):
            raw_finish_reason_value = response.candidates[0].finish_reason
            if hasattr(raw_finish_reason_value, 'name'):
                finish_reason_display_str = raw_finish_reason_value.name
            else:
                finish_reason_display_str = str(raw_finish_reason_value)

        has_tool_call = False
        function_call_part = None
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    function_call_part = part.function_call
                    has_tool_call = True
                    finish_reason_display_str = "TOOL_CALLS"
                    break

        logging.info(f"Gemini response. finish_reason: {finish_reason_display_str}, raw_finish_reason_value: {raw_finish_reason_value}, has_tool_call: {has_tool_call}")

        if function_call_part:
            if function_call_part.name == "format_digest_selection":
                args = function_call_part.args
                logging.info(f"Gemini used tool 'format_digest_selection' with args (type: {type(args)}): {str(args)[:1000]}...")

                transformed_output = {}
                if isinstance(args, (MapComposite, dict)):
                    entries_list_proto = args.get("selected_digest_entries")
                    if isinstance(entries_list_proto, (RepeatedComposite, list)):
                        for entry_proto in entries_list_proto:
                            if isinstance(entry_proto, (MapComposite, dict)):
                                topic_name = entry_proto.get("topic_name")
                                headlines_proto = entry_proto.get("headlines")

                                headlines_python_list = []
                                if isinstance(headlines_proto, (RepeatedComposite, list)):
                                    for h_item in headlines_proto:
                                        headlines_python_list.append(str(h_item))

                                if isinstance(topic_name, str) and topic_name.strip() and headlines_python_list:
                                    transformed_output[topic_name.strip()] = headlines_python_list
                                else:
                                    logging.warning(f"Skipping invalid entry from tool: topic '{topic_name}', headlines '{headlines_python_list}'")
                            else:
                                logging.warning(f"Skipping non-dict/MapComposite item in 'selected_digest_entries' from tool: {type(entry_proto)}")
                    else:
                        logging.warning(f"'selected_digest_entries' from tool is not a list/RepeatedComposite or is missing. Type: {type(entries_list_proto)}")
                else:
                    logging.warning(f"Gemini tool call 'args' is not a MapComposite or dict. Type: {type(args)}")

                logging.info(f"Transformed output from Gemini tool call: {transformed_output}")
                return transformed_output
            else:
                logging.warning(f"Gemini called an unexpected tool: {function_call_part.name}")
                return {}
        elif response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            text_content = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
            if text_content.strip():
                logging.warning("Gemini did not use the tool, returned text instead. Attempting to parse.")
                parsed_json_fallback = safe_parse_json(text_content)
                # The returned value from Gemini is a dict of {topic: [headlines]}
                # Let's check if the parsed content matches this structure.
                if isinstance(parsed_json_fallback, dict) and "selected_digest_entries" in parsed_json_fallback:
                    # It seems the model might return JSON matching the tool structure, even in text.
                    # We should handle this gracefully.
                    entries = parsed_json_fallback.get("selected_digest_entries", [])
                    if isinstance(entries, list):
                        transformed_output = {}
                        for item in entries:
                            if isinstance(item, dict):
                                topic = item.get("topic_name")
                                headlines = item.get("headlines")
                                if isinstance(topic, str) and isinstance(headlines, list):
                                    transformed_output[topic] = headlines
                        if transformed_output:
                             logging.info(f"Successfully parsed tool-like structure from Gemini text response: {transformed_output}")
                             return transformed_output

                logging.warning(f"Could not parse Gemini's text response into expected format. Raw text: {text_content[:500]}")
                return {}
            else:
                 logging.warning("Gemini returned no usable function call and no parsable text content.")
                 return {}
        else:
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                logging.warning(f"Gemini response has prompt feedback: {response.prompt_feedback}")
            logging.warning(f"Gemini returned no candidates or no content parts.")
            return {}

    except Exception as e:
        logging.error(f"Error during Gemini API call or processing response: {e}", exc_info=True)
        return {}
    
def git_push_history_json(history_file_path, base_dir, zone_for_commit_msg):
    """Adds, commits (if history.json changed and was staged), and pushes to GitHub using .env credentials."""
    try:
        github_user = os.getenv("GITHUB_USER")
        github_token = os.getenv("GITHUB_TOKEN")
        github_email = os.getenv("GITHUB_EMAIL") # Optional, for commit authorship
        github_repository = os.getenv("GITHUB_REPOSITORY")  # Format: "owner/repo-name"

        if not all([github_user, github_token, github_repository]): # github_email is optional
            logging.error("GITHUB_USER, GITHUB_TOKEN, or GITHUB_REPOSITORY not set in .env. Skipping git operations.")
            return

        relative_history_file = os.path.relpath(history_file_path, base_dir)
        if not os.path.exists(history_file_path):
            logging.info(f"{history_file_path} not found. Skipping git operations.")
            return

        logging.info(f"Attempting git operations for {relative_history_file} from {base_dir}")

        git_env = os.environ.copy()
        # It's generally better to configure git user/email per repo or globally,
        # but can be set for the command if needed, though less common for commit authorship.
        # subprocess.run will inherit the environment.
        # For authorship, `git commit -m "message" --author="User Name <email@example.com>"` could be used,
        # or `git config user.name "..."` and `git config user.email "..."` run beforehand.
        # The current script tries to set config which is fine.

        if github_email:
            email_config_cmd = ["git", "-C", base_dir, "config", "user.email", github_email]
            subprocess.run(email_config_cmd, check=False, capture_output=True, text=True)
        if github_user: # Using GITHUB_USER as the commit author name.
            name_config_cmd = ["git", "-C", base_dir, "config", "user.name", github_user] # GITHUB_USER for name
            subprocess.run(name_config_cmd, check=False, capture_output=True, text=True)

        add_cmd = ["git", "-C", base_dir, "add", relative_history_file]
        add_process = subprocess.run(add_cmd, capture_output=True, text=True, check=False)
        if add_process.returncode != 0:
            # Log warning but proceed, commit will fail if add truly failed and nothing staged
            logging.warning(f"git add {relative_history_file} exited with code {add_process.returncode}: {add_process.stderr.strip()}. Proceeding.")

        commit_message = f"Automated: Update {os.path.basename(history_file_path)} {datetime.now(zone_for_commit_msg).strftime('%Y-%m-%d %H:%M:%S %Z')}"
        commit_cmd = ["git", "-C", base_dir, "commit", "-m", commit_message]
        commit_process = subprocess.run(commit_cmd, capture_output=True, text=True, check=False)

        if commit_process.returncode == 0:
            logging.info(f"Commit successful. Message: '{commit_message}'\n{commit_process.stdout.strip()}")
        elif ("nothing to commit" in commit_process.stdout.lower() or 
              "no changes added to commit" in commit_process.stdout.lower()):
            logging.info(f"No changes to commit for {relative_history_file}. Git output: {commit_process.stdout.strip()}")
            # If no changes for this file, we might still want to push if other commits are pending
            # or if the "everything up-to-date" check for push is sufficient.
            # For now, let's assume a push is attempted regardless of this specific commit's outcome.
        else:
            logging.error(f"git commit failed with code {commit_process.returncode}. Stderr: {commit_process.stderr.strip()}. Stdout: {commit_process.stdout.strip()}")
            # Decide if to return or still attempt push. Let's attempt push.

        remote_url = f"https://{github_user}:{github_token}@github.com/{github_repository}.git"
        current_branch = ""
        try:
            get_branch_cmd = ["git", "-C", base_dir, "rev-parse", "--abbrev-ref", "HEAD"]
            branch_process = subprocess.run(get_branch_cmd, capture_output=True, text=True, check=True)
            current_branch = branch_process.stdout.strip()
            if not current_branch or current_branch == "HEAD": # HEAD means detached state
                logging.error("Could not determine current git branch or in detached HEAD state. Skipping git push.")
                return
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to get current git branch: {e.stderr.strip()}. Skipping git push.")
            return
        except FileNotFoundError:
            logging.error("git command not found. Ensure Git is installed and in PATH.")
            return

        logging.info(f"Attempting git push to repository {github_repository} on branch {current_branch}...")
        push_cmd = ["git", "-C", base_dir, "push", remote_url, current_branch]
        push_process = subprocess.run(push_cmd, capture_output=True, text=True, check=False)
        
        if push_process.returncode == 0:
            logging.info(f"git push successful to {github_repository} branch {current_branch}.\n{push_process.stdout.strip()}")
        elif ("everything up-to-date" in push_process.stdout.lower() or
              "everything up-to-date" in push_process.stderr.lower()): # Check stderr too
            logging.info(f"git push: Everything up-to-date for {github_repository} branch {current_branch}.")
        else:
            # Avoid logging the token if the command itself is part of the error message from git.
            # Stderr should be somewhat safe.
            logging.error(f"git push to {github_repository} branch {current_branch} failed with code {push_process.returncode}. Stderr: {push_process.stderr.strip()}. Stdout: {push_process.stdout.strip()}")

    except FileNotFoundError: 
        logging.error("git command not found. Please ensure Git is installed and in your system's PATH.")
    except Exception as e:
        logging.error(f"An unexpected error occurred during git operations: {e}", exc_info=True)


def main():
    # Load the entire history log from the JSON file.
    history = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except json.JSONDecodeError:
            logging.warning(f"Could not decode {HISTORY_FILE}. Initializing empty history.")
            history = {}
        except Exception as e:
            logging.error(f"Error loading {HISTORY_FILE}: {e}. Initializing empty history.")

    # Create a separate, clean list of recent headlines for the LLM's context.
    MAX_HISTORY_HEADLINES_FOR_LLM = int(CONFIG.get("MAX_HISTORY_HEADLINES_FOR_LLM", 150))
    recent_headlines_for_llm = load_recent_headlines_from_history(history, MAX_HISTORY_HEADLINES_FOR_LLM)

    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            logging.error("Missing GEMINI_API_KEY. Exiting.")
            return

        # Initialize containers for this run
        headlines_to_send = {}
        full_articles_map = {}
        
        banned_terms = [k for k, v in OVERRIDES.items() if v == "ban"]
        articles_to_fetch_per_topic = int(CONFIG.get("ARTICLES_TO_FETCH_PER_TOPIC", 20))

        # --- HYBRID PRE-FILTERING STAGE ---
        for topic in TOPIC_WEIGHTS:
            articles_for_this_topic = fetch_articles_for_topic(topic, articles_to_fetch_per_topic)
            if not articles_for_this_topic:
                continue
            
            allowed_titles_for_topic = []
            for article in articles_for_this_topic:
                # Call the history check with the MATCH_THRESHOLD from your config.
                # REMEMBER to set this to a high value (e.g., 0.90) in your Google Sheet.
                if is_in_history(article["title"], history, MATCH_THRESHOLD):
                    logging.debug(f"Skipping (history match): {article['title']}")
                    continue
                
                if contains_banned_keyword(article["title"], banned_terms):
                    logging.debug(f"Skipping (banned keyword): {article['title']}")
                    continue
                
                allowed_titles_for_topic.append(article["title"])
                full_articles_map[normalize(article["title"])] = article 
            
            if allowed_titles_for_topic:
                headlines_to_send[topic] = allowed_titles_for_topic

        if not headlines_to_send:
            logging.info("No fresh, non-banned, non-duplicate headlines available. Nothing to send to LLM.")
            return

        total_headlines_candidate_count = sum(len(v) for v in headlines_to_send.values())
        logging.info(f"Sending {total_headlines_candidate_count} candidate headlines across {len(headlines_to_send)} topics to Gemini.")

        selected_digest_content = prioritize_with_gemini(
            headlines_to_send=headlines_to_send,
            digest_history=recent_headlines_for_llm,
            gemini_api_key=gemini_api_key,
            topic_weights=TOPIC_WEIGHTS,
            keyword_weights=KEYWORD_WEIGHTS,
            overrides=OVERRIDES
        )

        if not selected_digest_content or not isinstance(selected_digest_content, dict):
            logging.warning("Gemini returned no valid digest content. No email will be sent.")
            return
        
        final_digest_to_email = {}
        processed_normalized_titles = set()

        for topic, titles_from_gemini in selected_digest_content.items():
            if not isinstance(titles_from_gemini, list):
                logging.warning(f"Gemini output for topic '{topic}' is not a list. Skipping.")
                continue
            
            articles_for_email_topic = []
            for title_from_llm in titles_from_gemini[:MAX_ARTICLES_PER_TOPIC]:
                normalized_title_from_gemini = normalize(title_from_llm)
                if not normalized_title_from_gemini or normalized_title_from_gemini in processed_normalized_titles:
                    continue
                
                original_article_data = full_articles_map.get(normalized_title_from_gemini)
                if original_article_data:
                    articles_for_email_topic.append(original_article_data)
                    processed_normalized_titles.add(normalized_title_from_gemini)
                else:
                    found_fallback = False
                    for stored_norm_title, stored_article_data in full_articles_map.items():
                        if normalized_title_from_gemini in stored_norm_title or stored_norm_title in stored_article_data.get('title', ''):
                            if stored_norm_title not in processed_normalized_titles:
                                articles_for_email_topic.append(stored_article_data)
                                processed_normalized_titles.add(stored_norm_title)
                                logging.info(f"Fallback matched LLM title '{title_from_llm}' to stored article '{stored_article_data['title']}'")
                                found_fallback = True
                                break
                    if not found_fallback:
                        logging.warning(f"Could not find original article data for title '{title_from_llm}'. Skipping.")
            
            if articles_for_email_topic:
                final_digest_to_email[topic] = articles_for_email_topic

        if not final_digest_to_email:
            logging.info("No articles selected for the final email digest after processing. No email sent.")
            return

        # --- Email Sending Logic ---
        EMAIL_FROM = os.getenv("GMAIL_USER", "").encode("ascii", "ignore").decode()
        EMAIL_BCC_RAW = os.getenv("MAILTO", "").strip()
        EMAIL_BCC_LIST = [email.strip() for email in EMAIL_BCC_RAW.split(",") if email.strip()]
        recipients = list(set([EMAIL_FROM] + EMAIL_BCC_LIST)) if EMAIL_FROM else list(set(EMAIL_BCC_LIST))

        if not recipients:
             logging.error("No recipients configured. Cannot send email.")
             return

        SMTP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
        if not EMAIL_FROM or not SMTP_PASS:
            logging.error("GMAIL_USER or GMAIL_APP_PASSWORD not set. Cannot send email.")
            return

        html_body_parts = ["<h2>Your News Digest</h2>"]
        total_articles_in_digest = 0
        for topic, articles in final_digest_to_email.items():
            section = f'<h3 style="margin-top: 20px; margin-bottom: 5px; padding-bottom: 3px;">{html.escape(topic)}</h3>'
            article_html_parts = []
            for article in articles:
                total_articles_in_digest += 1
                try:
                    pub_dt_obj = parsedate_to_datetime(article["pubDate"])
                    date_str = to_user_timezone(pub_dt_obj).strftime("%a, %d %b %Y %I:%M %p %Z")
                except Exception:
                    date_str = "Date unavailable"
                article_html_parts.append(
                    f'<p style="margin: 0.4em 0 1.2em 0;">'
                    f'📰 <a href="{html.escape(article["link"])}" target="_blank" style="text-decoration:none; color:#0056b3;">{html.escape(article["title"])}</a><br>'
                    f'<span style="font-size: 0.9em; color: #555;">📅 {date_str}</span>'
                    f'</p>'
                )
            section += "".join(article_html_parts)
            html_body_parts.append(section)
        
        preferences_link = "https://docs.google.com/spreadsheets/d/1OjpsQEnrNwcXEWYuPskGRA5Jf-U8e_x0x3j2CKJualg/edit?usp=sharing"
        footer_info = f'{total_articles_in_digest} articles selected by Gemini from {total_headlines_candidate_count} candidates published in the last {MAX_ARTICLE_HOURS} hours, based on your <a href="{preferences_link}" target="_blank">preferences</a>.'
        html_body = f"<html><head><style>body {{font-family: sans-serif;}}</style></head><body>{''.join(html_body_parts)}<hr><p style=\"font-size:0.8em; color:#777;\">{footer_info}</p></body></html>"

        msg = EmailMessage()
        current_time_str = datetime.now(ZONE).strftime('%Y-%m-%d %I:%M %p %Z')
        msg["Subject"] = f"🗞️ News Digest – {current_time_str}"
        msg["From"] = EMAIL_FROM
        if EMAIL_FROM in recipients:
            msg["To"] = EMAIL_FROM
        if EMAIL_BCC_LIST:
            msg["Bcc"] = ", ".join(EMAIL_BCC_LIST)
        msg.set_content("This is the plain-text version of your news digest. Please enable HTML to view the formatted version.")
        msg.add_alternative(html_body, subtype="html")

        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(EMAIL_FROM, SMTP_PASS)
                server.send_message(msg)
            logging.info(f"Digest email sent successfully to: {recipients}.")

            # --- History Update Logic ---
            for topic, articles_sent in final_digest_to_email.items():
                if topic not in history: history[topic] = []
                current_titles_in_history = {normalize(a['title']) for a in history[topic]}
                for article in articles_sent:
                    if normalize(article['title']) not in current_titles_in_history:
                        history[topic].append({"title": article["title"], "pubDate": article["pubDate"]})
                history_per_topic_limit = int(CONFIG.get("HISTORY_PER_TOPIC_LIMIT", 40))
                if len(history[topic]) > history_per_topic_limit:
                    history[topic] = history[topic][-history_per_topic_limit:]

        except Exception as e:
            logging.error(f"Email sending failed: {e}", exc_info=True)

        # --- History Pruning and Saving ---
        history_retention_days = int(CONFIG.get("NEWSBOT_HISTORY_RETENTION_DAYS", 30))
        time_limit_utc = datetime.now(ZoneInfo("UTC")) - timedelta(days=history_retention_days)
        pruned_history = {}
        for topic, articles in history.items():
            valid_articles = []
            for article in articles:
                try:
                    pub_dt = parsedate_to_datetime(article["pubDate"])
                    if pub_dt.tzinfo is None: pub_dt = pub_dt.replace(tzinfo=ZoneInfo("UTC"))
                    if pub_dt >= time_limit_utc:
                        valid_articles.append(article)
                except Exception:
                    valid_articles.append(article) # Keep if date is malformed
            if valid_articles:
                pruned_history[topic] = valid_articles
        history = pruned_history

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        logging.info(f"History saved to {HISTORY_FILE}")

        if CONFIG.get("ENABLE_GIT_PUSH", False):
            git_push_history_json(HISTORY_FILE, BASE_DIR, ZONE)
        else:
            logging.info("Git push for history.json is disabled in config.")

    except Exception as e:
        logging.critical(f"An unhandled error occurred in main: {e}", exc_info=True)
    finally:
        if os.path.exists(LOCKFILE):
            os.remove(LOCKFILE)
        logging.info(f"Lockfile released. Script finished at {datetime.now(ZONE).strftime('%Y-%m-%d %H:%M:%S %Z')}")
             
if __name__ == "__main__":
    main()







