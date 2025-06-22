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
    nltk_data_path_options = [
        os.path.join(BASE_DIR, "nltk_data"), # For CI or bundled deployments
        os.path.expanduser("~/nltk_data")    # Standard user location
    ]
    download_target_dir = nltk_data_path_options[0] # Default to local project path
    
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
GEMINI_MODEL_NAME = CONFIG.get("GEMINI_MODEL_NAME", "gemini-1.5-flash-latest") # Added

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

def is_in_history(article_title, history):
    norm_title_tokens = set(normalize(article_title).split())
    if not norm_title_tokens:
        return False

    for articles_in_topic in history.values(): # history.values() are lists of article dicts
        for a in articles_in_topic: # a is an article dict {"title": "...", "pubDate": "..."}
            past_title = a.get("title", "")
            past_tokens = set(normalize(past_title).split())
            if not past_tokens:
                continue
            
            intersection_len = len(norm_title_tokens.intersection(past_tokens))
            union_len = len(norm_title_tokens.union(past_tokens))
            if union_len == 0: # Avoid division by zero if both titles are empty after normalization
                similarity = 1.0 if not norm_title_tokens and not past_tokens else 0.0
            else:
                similarity = intersection_len / union_len

            if similarity >= MATCH_THRESHOLD: # Use the globally defined MATCH_THRESHOLD
                logging.debug(f"Article '{article_title}' matched past article '{past_title}' with similarity {similarity:.2f}")
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

def prioritize_with_gemini(headlines_to_send: dict, user_preferences: str, gemini_api_key: str) -> dict:
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL_NAME, # Use configured model name
        tools=[SELECT_DIGEST_ARTICLES_TOOL] # Enable tool
    )
    
    # Using the exact prompt string provided by the user
    prompt = (
        "You are an expert news curator. Your task is to meticulously select and deduplicate the most relevant news topics and headlines "
        "for a user's email digest. You will be given user preferences and a list of candidate articles. "
        "Your goal is to produce a concise, high-quality digest adhering to strict criteria.\n\n"
        f"User Preferences:\n{user_preferences}\n\n"
        f"Available Topics and Headlines (candidate articles):\n{json.dumps(dict(sorted(headlines_to_send.items())), indent=2)}\n\n"
        "Core Selection and Prioritization Logic:\n"
        "1.  **Topic Importance (User-Defined):** First, identify topics that align with the user's preferences and assigned importance weights (1=lowest, 5=highest). This is the primary driver for topic selection.\n"
        "2.  **Headline Newsworthiness & Relevance:** Within those topics, select headlines that are genuinely newsworthy, factual, objective, and deeply informative for a U.S. audience.\n"
        "3.  **Recency:** For developing stories with multiple updates, generally prefer the latest headline that provides the most comprehensive information, unless an earlier headline offers unique critical insight not found later.\n\n"
        "Strict Filtering Criteria (Apply these *after* initial relevance assessment):\n\n"
        "*   **Output Limits:**\n"
        f"    - Select up to {MAX_TOPICS} topics.\n"
        f"    - For each selected topic, choose up to {MAX_ARTICLES_PER_TOPIC} headlines.\n"
        "*   **Aggressive Deduplication:**\n"
        "    - CRITICAL: If multiple headlines cover the *exact same core event, announcement, or substantively similar information*, even if from different sources or under different candidate topics, select ONLY ONE. Choose the most comprehensive, authoritative, or recent version. Do not include slight rephrasing of the same news.\n"
        "*   **Geographic Focus:**\n"
        "    - Focus on national (U.S.) or major international news.\n"
        "    - AVOID news that is *solely* of local interest (e.g., specific to a small town, county, or local community event) *unless* it has clear and direct national or major international implications relevant to a U.S. audience (e.g., a local protest that gains national attention due to presidential involvement and sparks a national debate).\n"
        "*   **Banned/Demoted Content:**\n"
        "    - Strictly REJECT any headlines containing terms flagged as 'banned' in user preferences.\n"
        "    - Headlines with 'demote' terms should be *strongly deprioritized* (effectively treated as having an importance score of 0.1 on a 1-5 scale) and only selected if their relevance and importance are exceptionally high and no other suitable headlines exist for a critical user topic.\n" # Note: DEMOTE_FACTOR value is embedded here.
        "*   **Commercial Content:**\n"
        "    - REJECT advertisements.\n"
        "    - REJECT mentions of specific products/services UNLESS it's highly newsworthy criticism, a major market-moving announcement (e.g., a massive product recall by a major company), or a significant technological breakthrough discussed in a news context, not a promotional one.\n"
        "    - STRICTLY REJECT articles that primarily offer investment advice, promote specific stocks/cryptocurrencies as 'buy now' opportunities, or resemble 'hot stock tips' (e.g., \"Top X Stocks to Invest In,\" \"This Coin Will Explode,\" \"X Stocks Worth Buying\"). News about broad market trends (e.g., \"S&P 500 reaches record high\"), significant company earnings reports (without buy/sell advice), or major regulatory changes affecting financial markets IS acceptable. The key is to avoid direct or implied investment solicitation for specific securities.\n"
        "*   **Content Quality & Style:**\n"
        "    - Ensure a healthy diversity of subjects if possible within the user's preferences; do not let one single event (even if important) dominate the entire digest if other relevant news is available.\n"
        "    - PRIORITIZE content-rich, factual, objective, and neutrally-toned reporting.\n"
        "    - ACTIVELY AVOID and DEPRIORITIZE headlines that are:\n"
        "        - Sensationalist, using hyperbole, excessive superlatives (e.g., \"terrifying,\" \"decimated,\" \"gross failure\"), or fear-mongering.\n"
        "        - Purely for entertainment, celebrity gossip (unless of undeniable major national/international impact, e.g., death of a global icon), or \"fluff\" pieces lacking substantial news value (e.g., \"Recession Nails,\" \"Trump stumbles\").\n"
        "        - Clickbait (e.g., withholding key information, using vague teasers like \"You won't believe what happened next!\").\n"
        "        - Primarily opinion/op-ed pieces, especially those with inflammatory or biased language. Focus on reported news.\n"
        "        - Phrased as questions (e.g., \"Is X the new Y?\") or promoting listicles (e.g., \"5 reasons why...\"), unless the underlying content is exceptionally newsworthy and unique.\n"
        "*   **Overall Goal:** The selected articles must reflect genuine newsworthiness and be relevant to an informed general audience seeking serious, objective news updates.\n\n"
        "**Final Output Structure and Ordering:**\n"
        "When you provide your selections using the 'format_digest_selection' tool, you MUST adhere to the following ordering:\n"
        "1.  **Topic Order:** The selected topics MUST be ordered from most significant to least significant. Topic significance is determined primarily by user preference weights, but also consider the overall impact and newsworthiness of the actual headlines selected for that topic. The topic you deem most important overall for the user should appear first.\n"
        "2.  **Headline Order (within each topic):** For each selected topic, the chosen headlines MUST be ordered from most significant/newsworthy/comprehensive to least significant. This internal ordering should reflect the 'Headline Newsworthiness & Relevance' and 'Recency' criteria. The single most impactful headline for that topic should be listed first under that topic.\n\n"
        "Chain-of-Thought Instruction (Internal Monologue):\n"
        "Before finalizing, briefly review your choices against these criteria. Ask yourself:\n"
        "- \"Is this headline truly distinct from others I've selected?\"\n"
        "- \"Is this purely local, or does it have wider significance?\"\n"
        "- \"Is this trying to sell me a stock or just reporting market news?\"\n"
        "- \"Is this headline objective, or is it heavily opinionated/sensational?\"\n"
        "- \"Have I ordered my selected topics and the headlines within them correctly according to their significance?\"\n\n"
        "Based on all the above, provide your selections using the 'format_digest_selection' tool."
    )

    logging.info("Sending request to Gemini for prioritization using tool calling.")
    try:
        response = model.generate_content(
            [prompt], # Content can be a list
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
                    finish_reason_display_str = "TOOL_CALLS" # Override if tool call is present
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
                                    # Python dicts preserve insertion order (3.7+), so LLM's ordering is maintained
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
                logging.debug(f"Gemini raw text response: {text_content}")
                parsed_json_fallback = safe_parse_json(text_content)
                if isinstance(parsed_json_fallback, dict): # Ensure it's a dict
                    # Further validation if it matches expected structure could be added here
                    logging.info(f"Successfully parsed text fallback from Gemini: {parsed_json_fallback}")
                    return parsed_json_fallback
                else:
                    logging.warning(f"Parsed text fallback from Gemini did not result in a dict. Type: {type(parsed_json_fallback)}")
                    return {}
            else:
                 logging.warning("Gemini returned no usable function call and no parsable text content.")
                 if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                     logging.warning(f"Prompt feedback: {response.prompt_feedback}")
                 return {}
        else:
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                logging.warning(f"Gemini response has prompt feedback: {response.prompt_feedback}")
            logging.warning(f"Gemini returned no candidates or no content parts. Full response object: {response}")
            return {}

    except Exception as e:
        logging.error(f"Error during Gemini API call or processing response: {e}", exc_info=True)
        try:
            if 'response' in locals() and response:
                logging.error(f"Gemini response object on error (prompt_feedback): {response.prompt_feedback if hasattr(response, 'prompt_feedback') else 'N/A'}")
        except Exception as e_log:
            logging.error(f"Error logging response details during exception: {e_log}")
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
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f: # Added encoding
                history = json.load(f)
        except json.JSONDecodeError:
            logging.warning(f"Could not decode {HISTORY_FILE}. Initializing empty history.")
            history = {}
        except Exception as e: # Catch other potential IOErrors
            logging.error(f"Error loading {HISTORY_FILE}: {e}. Initializing empty history.")
            history = {}
    else:
        history = {}

    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            logging.error("Missing GEMINI_API_KEY. Exiting.")
            return # Exit main if no API key

        user_preferences = build_user_preferences(TOPIC_WEIGHTS, KEYWORD_WEIGHTS, OVERRIDES)
        headlines_to_send = {} # For LLM: topic -> list of titles
        full_articles_map = {} # For local use: normalized_title -> full article dict
        
        # Ensure banned_terms list uses the same keys as OVERRIDES (already lowercased during load)
        banned_terms = [k for k, v in OVERRIDES.items() if v == "ban"]


        articles_to_fetch_per_topic = int(CONFIG.get("ARTICLES_TO_FETCH_PER_TOPIC", 20)) # Configurable fetch count

        for topic in TOPIC_WEIGHTS: # Iterate actual topic names
            articles_for_this_topic = fetch_articles_for_topic(topic, articles_to_fetch_per_topic)
            if not articles_for_this_topic:
                continue
            
            allowed_titles_for_topic = []
            for article in articles_for_this_topic:
                # Pass the list of banned terms directly
                if is_in_history(article["title"], history) or contains_banned_keyword(article["title"], banned_terms):
                    logging.debug(f"Skipping article: '{article['title']}' (in history or banned).")
                    continue
                allowed_titles_for_topic.append(article["title"])
                # Use normalized title as key for robust matching later
                full_articles_map[normalize(article["title"])] = article 
            
            if allowed_titles_for_topic:
                headlines_to_send[topic] = allowed_titles_for_topic

        if not headlines_to_send:
            logging.info("No fresh, non-banned headlines available after initial filtering. Nothing to send to LLM.")
            # Consider if an email should still be sent saying "no news today" or just exit. Current exits.
            return

        total_headlines_candidate_count = sum(len(v) for v in headlines_to_send.values())
        logging.info(f"Sending {total_headlines_candidate_count} candidate headlines across {len(headlines_to_send)} topics to Gemini.")

        selected_digest_content = prioritize_with_gemini(headlines_to_send, user_preferences, gemini_api_key)

        if not selected_digest_content or not isinstance(selected_digest_content, dict):
            logging.info("Gemini returned no valid digest content or content was not a dictionary. No email will be sent.")
            return # Exit if Gemini provides nothing usable
        
        final_digest_to_email = {} # This will store Topic -> [Full Article Dicts]
        processed_normalized_titles = set() # For de-duplication across topics from Gemini's output

        # Gemini is expected to return topics and headlines already ordered by significance
        # Python dicts (3.7+) preserve insertion order, so this order will be maintained.
        for topic, titles_from_gemini in selected_digest_content.items():
            if not isinstance(titles_from_gemini, list):
                logging.warning(f"Gemini output for topic '{topic}' is not a list: {titles_from_gemini}. Skipping topic.")
                continue
            
            articles_for_email_topic = []
            for title_from_llm in titles_from_gemini: # Iterate titles in the order Gemini provided
                if not isinstance(title_from_llm, str):
                    logging.warning(f"Encountered non-string title in Gemini output for topic '{topic}': {title_from_llm}. Skipping.")
                    continue
                
                normalized_title_from_gemini = normalize(title_from_llm)
                if not normalized_title_from_gemini: # Skip if title normalizes to empty
                    logging.debug(f"Skipping LLM title '{title_from_llm}' as it normalized to empty string.")
                    continue

                if normalized_title_from_gemini in processed_normalized_titles:
                    logging.info(f"Skipping already processed (duplicate via normalization) title '{title_from_llm}' (norm: '{normalized_title_from_gemini}') from Gemini for topic '{topic}'.")
                    continue
                
                original_article_data = full_articles_map.get(normalized_title_from_gemini)
                if original_article_data:
                    articles_for_email_topic.append(original_article_data)
                    processed_normalized_titles.add(normalized_title_from_gemini)
                else:
                    # Fallback attempt if exact normalized match failed (e.g., LLM slightly rephrased)
                    # This can be risky; consider Jaccard similarity for more robust fuzzy matching if needed.
                    found_fallback = False
                    for stored_norm_title, stored_article_data in full_articles_map.items():
                        if normalized_title_from_gemini in stored_norm_title or stored_norm_title in normalized_title_from_gemini:
                            if stored_norm_title not in processed_normalized_titles:
                                articles_for_email_topic.append(stored_article_data)
                                processed_normalized_titles.add(stored_norm_title) # Add the matched stored title's norm
                                logging.info(f"Fallback matched LLM title '{title_from_llm}' (norm: '{normalized_title_from_gemini}') to stored article '{stored_article_data['title']}' (norm: '{stored_norm_title}')")
                                found_fallback = True
                                break
                    if not found_fallback:
                        logging.warning(f"Could not find original article data for title '{title_from_llm}' (normalized: '{normalized_title_from_gemini}') from Gemini. It might have been rephrased significantly or is not from candidates. Skipping.")
            
            if articles_for_email_topic:
                final_digest_to_email[topic] = articles_for_email_topic

        if not final_digest_to_email:
            logging.info("No articles selected for the final email digest after Gemini processing and mapping. No email sent.")
            return

        # --- Email Sending Logic ---
        EMAIL_FROM = os.getenv("GMAIL_USER", "").encode("ascii", "ignore").decode()
        EMAIL_TO_SELF = EMAIL_FROM # Default to send to self if GMAIL_USER is set
        EMAIL_BCC_RAW = os.getenv("MAILTO", "").strip()
        EMAIL_BCC_LIST = [email.strip() for email in EMAIL_BCC_RAW.split(",") if email.strip()]
        
        recipients = []
        if EMAIL_TO_SELF:
            recipients.append(EMAIL_TO_SELF)
        recipients.extend(EMAIL_BCC_LIST)
        recipients = list(set(recipients)) # Deduplicate

        if not recipients:
             logging.error("No recipients configured (GMAIL_USER is empty and MAILTO is empty or invalid). Cannot send email.")
             return

        SMTP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
        SMTP_SERVER = "smtp.gmail.com"
        SMTP_PORT = 587

        if not EMAIL_FROM or not SMTP_PASS: # EMAIL_FROM is used for login
            logging.error("GMAIL_USER (for login) or GMAIL_APP_PASSWORD not set. Cannot send email.")
            return

        html_body_parts = ["<h2>Your News Digest</h2>"]
        total_articles_in_digest = 0
        for topic, articles in final_digest_to_email.items(): # Iterates in Gemini's provided order
            section = f'<h3 style="margin-top: 20px; margin-bottom: 5px; padding-bottom: 3px; border-bottom: 1px solid #eee;">{html.escape(topic)}</h3>'
            article_html_parts = []
            for article in articles: # Iterates in Gemini's provided order for headlines
                total_articles_in_digest += 1
                try:
                    pub_dt_obj = parsedate_to_datetime(article["pubDate"])
                    pub_dt_user_tz = to_user_timezone(pub_dt_obj)
                    date_str = pub_dt_user_tz.strftime("%a, %d %b %Y %I:%M %p %Z")
                except Exception:
                    date_str = "Date unavailable" # Fallback
                article_html_parts.append(
                    f'<p style="margin: 0.4em 0 1.2em 0;">'
                    f'📰 <a href="{html.escape(article["link"])}" target="_blank" style="text-decoration:none; color:#0056b3;">{html.escape(article["title"])}</a><br>'
                    f'<span style="font-size: 0.9em; color: #555;">📅 {date_str}</span>'
                    f'</p>'
                )
            section += "".join(article_html_parts)
            html_body_parts.append(section)
        
        html_body_content = "".join(html_body_parts)
        # Using the exact Google Sheet link from the first script's footer for preferences
        preferences_link = "https://docs.google.com/spreadsheets/d/1OjpsQEnrNwcXEWYuPskGRA5Jf-U8e_x0x3j2CKJualg/edit?usp=sharing"
        footer_info = f'{total_articles_in_digest} articles selected by Gemini from {total_headlines_candidate_count} candidates published in the last {MAX_ARTICLE_HOURS} hours, based on your <a href="{preferences_link}" target="_blank">preferences</a>.'
        html_body = f"<html><head><style>body {{font-family: sans-serif;}}</style></head><body>{html_body_content}<hr><p style=\"font-size:0.8em; color:#777;\">{footer_info}</p></body></html>"


        msg = EmailMessage()
        current_time_str = datetime.now(ZONE).strftime('%Y-%m-%d %I:%M %p %Z')
        msg["Subject"] = f"🗞️ News Digest – {current_time_str}"
        msg["From"] = EMAIL_FROM
        
        # Set To and Bcc. EmailMessage handles multiple addresses in Bcc if comma-separated.
        # For clarity, send to GMAIL_USER if it's the primary, and BCC others.
        # Or, if only BCC list, just use that.
        if EMAIL_TO_SELF and EMAIL_TO_SELF in recipients:
            msg["To"] = EMAIL_TO_SELF
            # Remove from BCC list if it's already in To
            if EMAIL_TO_SELF in EMAIL_BCC_LIST:
                EMAIL_BCC_LIST.remove(EMAIL_TO_SELF)
        
        if EMAIL_BCC_LIST: # Remaining BCC recipients
            msg["Bcc"] = ", ".join(EMAIL_BCC_LIST)
        
        # If msg["To"] is still empty (e.g. GMAIL_USER was not meant to be a recipient, only MAILTO)
        # and there are BCC recipients, that's fine. If both are empty, error.
        if not msg.get("To") and not msg.get("Bcc"):
            logging.error("No valid recipients for email after processing To/Bcc. This shouldn't happen if initial check passed.")
            return

        msg.set_content("This is the plain-text version of your news digest. Please enable HTML to view the formatted version.")
        msg.add_alternative(html_body, subtype="html")

        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_FROM, SMTP_PASS)
                server.send_message(msg)
            logging.info(f"Digest email sent successfully at {current_time_str} to: {recipients}.")

            # --- History Update ---
            for topic, articles_sent in final_digest_to_email.items():
                topic_key_in_history = topic # Using the topic name as key
                if topic_key_in_history not in history:
                    history[topic_key_in_history] = []
                
                # Create a set of normalized titles already in history for this topic for efficient check
                current_normalized_titles_in_history = {normalize(a['title']) for a in history[topic_key_in_history]}
                
                for article_to_add in articles_sent:
                    # Add only if not already present (based on normalized title)
                    if normalize(article_to_add['title']) not in current_normalized_titles_in_history:
                        history[topic_key_in_history].append({
                            "title": article_to_add["title"], # Store original title
                            "pubDate": article_to_add["pubDate"] # Store original pubDate
                        })
                        current_normalized_titles_in_history.add(normalize(article_to_add['title'])) # Update set
                
                # Optional: limit history per topic to last N items (e.g., 40)
                # This is different from time-based pruning but can prevent one topic from bloating history.
                history_per_topic_limit = int(CONFIG.get("HISTORY_PER_TOPIC_LIMIT", 40))
                if len(history[topic_key_in_history]) > history_per_topic_limit:
                    history[topic_key_in_history] = history[topic_key_in_history][-history_per_topic_limit:]

        except smtplib.SMTPAuthenticationError:
            logging.error("SMTP Authentication Error. Check GMAIL_USER and GMAIL_APP_PASSWORD.")
        except Exception as e:
            logging.error(f"Email sending failed: {e}", exc_info=True)

        # --- History Pruning (time-based) ---
        # Using a fixed 30-day retention for this script as per original logic.
        # Can be made configurable similar to HISTORY_RETENTION_DAYS if desired.
        history_retention_days_newsbot = int(CONFIG.get("NEWSBOT_HISTORY_RETENTION_DAYS", 30))
        one_month_ago_utc = datetime.now(ZoneInfo("UTC")) - timedelta(days=history_retention_days_newsbot)
        
        logging.info(f"Pruning history older than {history_retention_days_newsbot} days (before {one_month_ago_utc.isoformat()}).")
        pruned_article_count = 0
        kept_article_count = 0

        for topic_key in list(history.keys()): # Iterate over copy of keys for safe deletion
            pruned_articles_for_topic = []
            for article_entry in history[topic_key]:
                try:
                    pub_dt_naive = parsedate_to_datetime(article_entry["pubDate"]) # pubDate is string
                    pub_dt_utc = pub_dt_naive.astimezone(ZoneInfo("UTC")) if pub_dt_naive.tzinfo else pub_dt_naive.replace(tzinfo=ZoneInfo("UTC"))
                    
                    if pub_dt_utc >= one_month_ago_utc:
                        pruned_articles_for_topic.append(article_entry)
                        kept_article_count += 1
                    else:
                        pruned_article_count += 1
                except Exception as e:
                    # If date is malformed, keep it to be safe, or decide to discard. Keeping is safer.
                    logging.warning(f"Skipping article in history due to malformed pubDate '{article_entry.get('pubDate')}' for title '{article_entry.get('title')}': {e}. Keeping.")
                    pruned_articles_for_topic.append(article_entry)
                    kept_article_count += 1

            if pruned_articles_for_topic:
                history[topic_key] = pruned_articles_for_topic
            else: # All articles for this topic were pruned
                logging.info(f"Removing empty topic '{topic_key}' from history after pruning.")
                del history[topic_key]
        
        logging.info(f"History pruning complete. Kept: {kept_article_count}, Pruned: {pruned_article_count} articles.")

        with open(HISTORY_FILE, "w", encoding="utf-8") as f: # Added encoding
            json.dump(history, f, indent=2)
        logging.info(f"History saved to {HISTORY_FILE}")

        if CONFIG.get("ENABLE_GIT_PUSH", False): # Use a config flag for this
            git_push_history_json(HISTORY_FILE, BASE_DIR, ZONE)
        else:
            logging.info("Git push for history.json is disabled in config.")

    except Exception as e:
        logging.critical(f"An unhandled error occurred in main: {e}", exc_info=True)
    finally:
        # nltk_data cleanup logic was commented out in original, keeping it that way.
        # if os.path.exists(nltk_home_dir): 
        # try:
        # shutil.rmtree(nltk_home_dir)
        # logging.info(f"Cleaned up local nltk_data directory: {nltk_home_dir}")
        # except Exception as e:
        # logging.warning(f"Failed to delete local nltk_data directory {nltk_home_dir}: {e}")

        if os.path.exists(LOCKFILE):
            os.remove(LOCKFILE)
        logging.info(f"Lockfile released. Script finished at {datetime.now(ZONE).strftime('%Y-%m-%d %H:%M:%S %Z')}")

if __name__ == "__main__":
    main()