# Author: Blake Rayvid <https://github.com/brayvid>
#!/usr/bin/env python3
import os
import sys
import csv
import json
import smtplib
import requests
import html
import logging
from datetime import datetime, timedelta
from email.message import EmailMessage
import xml.etree.ElementTree as ET
import atexit

LOCKFILE = "/tmp/digest_bot.lock"

if os.path.exists(LOCKFILE):
    print("Script is already running. Exiting.")
    sys.exit()
else:
    with open(LOCKFILE, 'w') as f:
        f.write("locked")

def cleanup():
    if os.path.exists(LOCKFILE):
        os.remove(LOCKFILE)
        print("Lockfile released by cleanup.")
atexit.register(cleanup)

try:
    # ─── Logging Setup ─────────────────────────────────────────────────────
    BASE_DIR = os.path.dirname(__file__)
    LOG_PATH = os.path.join(BASE_DIR, "logs/digest.log")
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO)
    logging.info(f"Cron ran at {datetime.now()}")

    # ─── Config / Environment ──────────────────────────────────────────────
    EMAIL_FROM = os.getenv("GMAIL_USER", "").encode("ascii", "ignore").decode()
    EMAIL_TO = os.getenv("MAILTO", EMAIL_FROM).encode("ascii", "ignore").decode()
    SMTP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587

    TOPIC_CSV = os.path.join(BASE_DIR, "topics.csv")
    LAST_SEEN_FILE = os.path.join(BASE_DIR, "last_seen.json")

    # ─── Load Previous State ───────────────────────────────────────────────
    if os.path.exists(LAST_SEEN_FILE):
        with open(LAST_SEEN_FILE, "r") as f:
            last_seen = json.load(f)
    else:
        last_seen = {}

    # ─── Read Topics ───────────────────────────────────────────────────────
    with open(TOPIC_CSV, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        topics = [row[0].strip() for row in reader if row]

    # ─── Fetch Articles & Build Digest ─────────────────────────────────────
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    digest_entries = []

    for topic in topics:
        feed_url = f"https://news.google.com/rss/search?q={requests.utils.quote(topic)}"

        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(feed_url, headers=headers, timeout=10)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            item = root.find("./channel/item") or root.find("{http://www.w3.org/2005/Atom}entry")

            if item is None:
                continue

            title = item.findtext("title") or "No title"
            link = item.findtext("link")
            if link is None:
                atom_link = item.find("{http://www.w3.org/2005/Atom}link")
                link = atom_link.attrib.get("href") if atom_link is not None else None

            pubDate = item.findtext("pubDate") or item.findtext("{http://www.w3.org/2005/Atom}updated")
            pubDate_dt = datetime.strptime(pubDate, "%a, %d %b %Y %H:%M:%S %Z") if pubDate else None

            topic_key = topic.replace(" ", "_").lower()

            last_seen_entry = last_seen.get(topic_key, {})
            last_seen_date_str = last_seen_entry.get("pubDate", "")
            last_seen_title = last_seen_entry.get("title", "")

            try:
                last_seen_date = datetime.strptime(last_seen_date_str, "%a, %d %b %Y %H:%M:%S %Z")
            except:
                last_seen_date = datetime.min

            if (
                pubDate_dt
                and pubDate_dt > last_seen_date
                and pubDate_dt > one_week_ago
                and title != last_seen_title
            ):
                digest_entries.append(f"""
                    <p>
                        🗂️ <strong>{html.escape(topic)}</strong><br>
                        📰 <a href="{link}" target="_blank">{html.escape(title)}</a><br>
                        📅 {pubDate}
                    </p>
                """)
                last_seen[topic_key] = {
                    "title": title,
                    "pubDate": pubDate
                }

        except Exception as e:
            logging.warning(f"Error fetching topic '{topic}': {e}")
            continue

    # ─── Send Email Digest ─────────────────────────────────────────────────
    if digest_entries:
        html_body = "<h2>Your Daily Digest</h2>\n" + "\n".join(digest_entries)

        msg = EmailMessage()
        msg["Subject"] = f"🗞️ Daily Digest – {datetime.now().strftime('%Y-%m-%d')}"
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg.set_content("This is the plain-text version of your weekly digest.")
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
        logging.info("No new articles to send.")

    # ─── Save State ────────────────────────────────────────────────────────
    with open(LAST_SEEN_FILE, "w") as f:
        json.dump(last_seen, f, indent=2)

finally:
    if os.path.exists(LOCKFILE):
        os.remove(LOCKFILE)
    logging.info("Lockfile released by script.")
