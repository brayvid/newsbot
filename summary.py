# Author: Blake Rayvid <https://github.com/brayvid/based-news>

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import google.generativeai as genai
import subprocess
import requests
import csv
from email.message import EmailMessage
import smtplib

# --- START: Script-wide constants ---
CONFIG_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTWCrmL5uXBJ9_pORfhESiZyzD3Yw9ci0Y-fQfv0WATRDq6T8dX0E7yz1XNfA6f92R7FDmK40MFSdH4/pub?gid=446667252&single=true&output=csv"
BASE_DIR = os.path.dirname(__file__) or "."
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
LOGFILE = os.path.join(BASE_DIR, "logs/summary.log")
SUMMARIES_FILE = os.path.join(BASE_DIR, "summaries.json")
# --- END: Script-wide constants ---

# --- Setup ---
os.makedirs(os.path.dirname(LOGFILE), exist_ok=True)

# --- Logging ---
logging.basicConfig(
    filename=LOGFILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.info("--- Summary script started ---")

# --- Load environment ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- MODIFIED: Git Sync Function at the beginning ---
def sync_repository():
    """Ensures the local repository is clean and up-to-date before proceeding."""
    try:
        logging.info("Synchronizing repository with remote...")
        GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
        GITHUB_USER = os.getenv("GITHUB_USER", "your-username")
        REPO = "newsbot"
        REPO_OWNER = "brayvid"

        if not all([GITHUB_TOKEN, GITHUB_USER, REPO, REPO_OWNER]):
            logging.error("Git credentials or repo info missing in environment. Skipping sync.")
            return

        remote_url = f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{REPO_OWNER}/{REPO}.git"

        # Hard reset to discard any lingering changes from a failed previous run.
        # This is safe because we are about to generate a fresh summary anyway.
        subprocess.run(["git", "fetch", "origin"], check=True, cwd=BASE_DIR)
        subprocess.run(["git", "reset", "--hard", "origin/main"], check=True, cwd=BASE_DIR)
        
        # Configure remote and pull latest changes
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True, cwd=BASE_DIR)
        subprocess.run(["git", "pull", "origin", "main", "--rebase"], check=True, cwd=BASE_DIR)
        
        logging.info("Repository synchronized successfully.")
    except Exception as e:
        logging.critical(f"Fatal: Git sync failed: {e}. Exiting script.")
        sys.exit(1)

# --- Execute Git Sync at the start of the script ---
sync_repository()


def load_config_from_sheet(url):
    config = {}
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        reader = csv.reader(response.text.splitlines())
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                key, val = row[0].strip(), row[1].strip()
                try:
                    config[key] = float(val) if '.' in val else int(val)
                except ValueError:
                    config[key] = val
        logging.info("Successfully loaded config from Google Sheet.")
        return config
    except Exception as e:
        logging.error(f"Failed to load config from {url}: {e}")
        return None

CONFIG = load_config_from_sheet(CONFIG_CSV_URL)
if CONFIG is None:
    logging.critical("Fatal: Unable to load CONFIG from sheet. Exiting.")
    sys.exit(1)

USER_TIMEZONE = CONFIG.get("TIMEZONE", "America/New_York")
try:
    ZONE = ZoneInfo(USER_TIMEZONE)
except Exception:
    logging.warning(f"Invalid TIMEZONE '{USER_TIMEZONE}'. Falling back to 'America/New_York'")
    ZONE = ZoneInfo("America/New_York")

# --- Load history ---
try:
    with open(HISTORY_FILE, "r") as f:
        history_data = json.load(f)
    logging.info(f"Successfully loaded history file: {HISTORY_FILE}")
except Exception as e:
    logging.critical(f"Failed to load history.json: {e}")
    sys.exit(1)

def filter_history_last_7_days(data):
    """Filters history, handling multiple date formats."""
    filtered_data = {}
    now_utc = datetime.now(ZoneInfo("UTC"))
    seven_days_ago = now_utc - timedelta(days=7)
    for topic, articles in data.items():
        recent_articles = []
        for article in articles:
            pub_date_str = article.get('pubDate')
            if not pub_date_str: continue
            try:
                article_date = None
                try:
                    article_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z')
                    article_date = article_date.astimezone(ZoneInfo("UTC"))
                except ValueError:
                    article_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
                if article_date.tzinfo is None:
                    article_date = article_date.replace(tzinfo=ZoneInfo("UTC"))
                if article_date >= seven_days_ago:
                    recent_articles.append(article)
            except (ValueError, KeyError) as e:
                logging.warning(f"Skipping article due to unparsable date: '{pub_date_str}' ({e})")
                continue
        if recent_articles:
            filtered_data[topic] = recent_articles
    return filtered_data

history_data_filtered = filter_history_last_7_days(history_data)
logging.info("Filtered history to only include headlines from the last 7 days.")

def format_history(data):
    if not data: return "No recent headlines found in the last 7 days."
    parts = []
    for topic, articles in data.items():
        parts.append(f"### {topic.title()}")
        for a in articles:
            parts.append(f"- {a.get('title', 'No Title')} ({a.get('pubDate', 'No Date')})")
    return "\n".join(parts)

# --- Gemini query ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# <<< MODIFICATION START: Replaced the old prompt with the enhanced, fact-checking prompt >>>
question = (
    "Give a brief report with short paragraphs in roughly 100 words on how the world has been doing lately based on the attached headlines. "
    "**Use Google Search to actively verify all information, such as names, places, figures, and event details to ensure the summary is factually accurate and grounded in real-world information, not just inferences from the headlines.** "
    "Use simple language, cite figures, and be specific with people, places, things, etc. "
    "Do not use bullet points and do not use section headings or any markdown formatting. Use only complete sentences. "
    "State the timeframe being discussed. Don't state that it's a report, simply present the findings. "
    "At the end, in 50 words, using all available clues in the headlines and your search findings, predict what should in all likelihood occur in the near future, and less likely but still entirely possible events, and give a sense of the ramifications."
)
# <<< MODIFICATION END >>>

try:
    # <<< MODIFICATION START: Enabled grounding in the API call with the correct syntax >>>
    logging.info("Sending prompt to Gemini with grounding enabled...")
    prompt = f"{question}\n\n{format_history(history_data_filtered)}"
    
    # Correctly create the grounding tool using the proper path
    tools = [genai.types.Tool(google_search_retrieval={})]

    # Pass the tool in the `tools` parameter
    result = model.generate_content(prompt, tools=tools)
    # <<< MODIFICATION END >>>

    answer = result.text.strip()
    logging.info("Gemini returned a response.")
except Exception as e:
    logging.error(f"Gemini request failed: {e}")
    sys.exit(1)

formatted = answer.replace('\n', '<br>')

# --- Compose and send email ---
EMAIL_FROM = os.getenv("GMAIL_USER", "").encode("ascii", "ignore").decode()
EMAIL_BCC = os.getenv("MAILTO", "").strip()
SMTP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
if EMAIL_FROM and SMTP_PASS and EMAIL_BCC:
    msg = EmailMessage()
    msg["Subject"] = f"🗞️ Week In Review – {datetime.now(ZONE).strftime('%Y-%m-%d')}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_FROM
    msg["Bcc"] = ", ".join([email.strip() for email in EMAIL_BCC.split(",") if email.strip()])
    msg.set_content("This is the plain-text version of your weekly outlook email.")
    msg.add_alternative(f"<p>{formatted}</p>", subtype="html")
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_FROM, SMTP_PASS)
            server.send_message(msg)
        logging.info("Digest email sent successfully.")
    except Exception as e:
        logging.error(f"Email failed: {e}")
else:
    logging.warning("Email credentials not fully configured. Skipping email.")

# --- Append summary to summaries.json ---
summary_entry = {"timestamp": datetime.now(ZONE).isoformat(), "summary": formatted}
try:
    summaries = []
    if os.path.exists(SUMMARIES_FILE):
        with open(SUMMARIES_FILE, "r", encoding="utf-8") as f:
            try:
                summaries = json.load(f)
            except json.JSONDecodeError:
                logging.warning("summaries.json is empty or corrupted. Starting new list.")
                summaries = []
    summaries.append(summary_entry)
    with open(SUMMARIES_FILE, "w", encoding="utf-8") as f:
        json.dump(summaries, f, indent=2, ensure_ascii=False)
    logging.info("Summary appended to summaries.json")
except Exception as e:
    logging.error(f"Failed to append to summaries.json: {e}")

# --- MODIFIED: Git Publish function at the end ---
def publish_changes():
    """Adds, commits, and pushes the generated summary to the remote repository."""
    try:
        logging.info("Publishing changes to repository...")
        subprocess.run(["git", "add", SUMMARIES_FILE], check=True, cwd=BASE_DIR)
        # Use --allow-empty to prevent errors if the file content is unchanged
        subprocess.run(["git", "commit", "-m", "Auto-update weekly summary", "--allow-empty"], check=True, cwd=BASE_DIR)
        subprocess.run(["git", "push"], check=True, cwd=BASE_DIR)
        logging.info("Summaries committed and pushed to GitHub.")
    except Exception as e:
        logging.error(f"Git publish failed: {e}")

# --- Execute Git Publish at the end of the script ---
publish_changes()

logging.info("--- Summary script finished ---\n")