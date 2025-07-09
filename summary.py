# Author: Blake Rayvid <https://github.com/brayvid/based-news>

import os
import sys
import json
import logging
from datetime import datetime, timedelta  # MODIFIED: Added timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import google.generativeai as genai
import subprocess
import requests
import csv
from email.message import EmailMessage
import smtplib

CONFIG_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTWCrmL5uXBJ9_pORfhESiZyzD3Yw9ci0Y-fQfv0WATRDq6T8dX0E7yz1XNfA6f92R7FDmK40MFSdH4/pub?gid=446667252&single=true&output=csv"

# --- Setup ---
BASE_DIR = os.path.dirname(__file__)
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
LOGFILE = os.path.join(BASE_DIR, "logs/summary.log")
os.makedirs(os.path.dirname(LOGFILE), exist_ok=True)

# --- Logging ---
# Configure logging to include timestamp, level, and message
logging.basicConfig(
    filename=LOGFILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.info("Summary script started.")

# --- Load environment ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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
        logging.info("Successfully loaded config from Google Sheet.")
        return config
    except Exception as e:
        logging.error(f"Failed to load config from {url}: {e}")
        return None

# Load config before main
CONFIG = load_config_from_sheet(CONFIG_CSV_URL)
if CONFIG is None:
    logging.critical("Fatal: Unable to load CONFIG from sheet. Exiting.")
    sys.exit(1)  # Stop immediately if config fails

# Load specified timezone to report in
USER_TIMEZONE = CONFIG.get("TIMEZONE", "America/New_York")
try:
    ZONE = ZoneInfo(USER_TIMEZONE)
except Exception:
    logging.warning(f"Invalid TIMEZONE '{USER_TIMEZONE}' in config. Falling back to 'America/New_York'")
    ZONE = ZoneInfo("America/New_York")

# Converts datetime to user timezone
def to_user_timezone(dt):
    return dt.astimezone(ZONE)

# --- Load history ---
try:
    with open(HISTORY_FILE, "r") as f:
        history_data = json.load(f)
    logging.info(f"Successfully loaded history file: {HISTORY_FILE}")
except Exception as e:
    logging.critical(f"Failed to load history.json: {e}")
    sys.exit(1)

# --- START: MODIFIED SECTION ---

# This new function filters the history to include only articles from the last 7 days.
def filter_history_last_7_days(data):
    """Filters history to include only articles published within the last 7 days."""
    filtered_data = {}
    now_utc = datetime.now(ZoneInfo("UTC"))
    seven_days_ago = now_utc - timedelta(days=7)

    for topic, articles in data.items():
        recent_articles = []
        for article in articles:
            try:
                # Parse the ISO format date string from the JSON file.
                article_date = datetime.fromisoformat(article['pubDate'])
                
                # Ensure the date is timezone-aware for correct comparison.
                # If it's naive, assume it's UTC, which is common for machine-generated timestamps.
                if article_date.tzinfo is None:
                    article_date = article_date.replace(tzinfo=ZoneInfo("UTC"))

                if article_date >= seven_days_ago:
                    recent_articles.append(article)
            except (ValueError, KeyError) as e:
                logging.warning(f"Skipping article due to date parse error or missing key: {e}")
                continue
        
        if recent_articles:
            filtered_data[topic] = recent_articles
            
    return filtered_data

# Apply the filter to the loaded history data
history_data_filtered = filter_history_last_7_days(history_data)
logging.info("Filtered history to only include headlines from the last 7 days.")

# --- END: MODIFIED SECTION ---

# --- Format history into plain text ---
def format_history(data):
    parts = []
    for topic, articles in data.items():
        parts.append(f"### {topic.title()}")
        for a in articles:
            parts.append(f"- {a['title']} ({a['pubDate']})")
    return "\n".join(parts)

# --- Gemini query ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

question = (
    "Give a brief report with short paragraphs in roughly 100 words on how the world has been doing lately based on the attached headlines. Use simple language, cite figures, and be specific with people, places, things, etc. Do not use bullet points and do not use section headings or any markdown formatting. Use only complete sentences. State the timeframe being discussed. Don't state that it's a report, simply present the findings. At the end, in 50 words, using all available clues in the headlines, predict what should in all likelihood occur in the near future, and less likely but still entirely possible events, and give a sense of the ramifications."
)

try:
    logging.info("Sending prompt to Gemini...")
    # MODIFIED: Use the filtered history data for the prompt
    prompt = f"{question}\n\n{format_history(history_data_filtered)}"
    result = model.generate_content(prompt)
    answer = result.text.strip()
    logging.info("Gemini returned a response.")

except Exception as e:
    logging.error(f"Gemini request failed: {e}")
    sys.exit(1)

# --- Format HTML output ---
formatted = answer.replace('\n', '<br>')
timestamp = datetime.now(ZONE).strftime("%A, %d %B %Y %I:%M %p %Z")
html_output = f"""<html>
  <body>
    <p>{formatted}</p>
    <div class='timestamp' id='summary-last-updated' style='display: none;'>Last updated: {timestamp}</div>
  </body>
</html>"""

# Compose and send email
EMAIL_FROM = os.getenv("GMAIL_USER", "").encode("ascii", "ignore").decode()
EMAIL_TO = EMAIL_FROM
EMAIL_BCC = os.getenv("MAILTO", "").strip()
EMAIL_BCC_LIST = [email.strip() for email in EMAIL_BCC.split(",") if email.strip()]
SMTP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

html_body = "<p>"+formatted+"</p>"

msg = EmailMessage()
msg["Subject"] = f"🗞️ Week In Review – {datetime.now(ZONE).strftime('%Y-%m-%d')}"
msg["From"] = EMAIL_FROM
msg["To"] = EMAIL_TO
msg["Bcc"] = ", ".join(EMAIL_BCC_LIST)
msg.set_content("This is the plain-text version of your weekly outlook email.")
msg.add_alternative(html_body, subtype="html")

try:
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_FROM, SMTP_PASS)
        server.send_message(msg)
    logging.info("Digest email sent successfully.")

except Exception as e:
    logging.error(f"Email failed: {e}")


# --- Append summary to summaries.json ---
SUMMARIES_FILE = os.path.join(BASE_DIR, "summaries.json")
summary_entry = {
    "timestamp": datetime.now(ZONE).isoformat(),
    "summary": formatted
}

try:
    if os.path.exists(SUMMARIES_FILE):
        with open(SUMMARIES_FILE, "r", encoding="utf-8") as f:
            summaries = json.load(f)
    else:
        summaries = []

    summaries.append(summary_entry)

    with open(SUMMARIES_FILE, "w", encoding="utf-8") as f:
        json.dump(summaries, f, indent=2, ensure_ascii=False)

    logging.info("Summary appended to summaries.json")

except Exception as e:
    logging.error(f"Failed to append to summaries.json: {e}")


# Git commit and push
try:
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    GITHUB_USER = os.getenv("GITHUB_USER", "your-username")
    REPO = "newsbot"
    REPO_OWNER = "brayvid"

    remote_url = f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{REPO_OWNER}/{REPO}.git"

    logging.info("Configuring git remote and pulling latest changes...")
    subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True, cwd=BASE_DIR)
    subprocess.run(["git", "pull", "origin", "main"], check=True, cwd=BASE_DIR)

    logging.info("Adding files to git...")
    subprocess.run(["git", "add", "summaries.json"], check=True, cwd=BASE_DIR)
    
    logging.info("Committing changes...")
    subprocess.run(["git", "commit", "-m", "Auto-update digest and history"], check=True, cwd=BASE_DIR)
    
    logging.info("Pushing changes to GitHub...")
    subprocess.run(["git", "push"], check=True, cwd=BASE_DIR)
    
    logging.info("Digest and history committed and pushed to GitHub.")
except Exception as e:
    logging.error(f"Git commit/push failed: {e}")

logging.info("Summary script finished.")