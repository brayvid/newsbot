#!/usr/bin/env python3
import os
import sys
import json
import logging
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv

# Define paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
LOCKFILE = os.path.join(BASE_DIR, "newsbot.lock")

# Setup logging
log_path = os.path.join(BASE_DIR, "logs/prune_history.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)
logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

load_dotenv(os.path.join(BASE_DIR, ".env"))

RETENTION_DAYS = 30


def git_push_history(history_file_path, base_dir):
    """Optional git commit and push if credentials exist in .env"""
    github_user = os.getenv("GITHUB_USER")
    github_token = os.getenv("GITHUB_TOKEN")
    github_repo = os.getenv("GITHUB_REPOSITORY")

    if not all([github_user, github_token, github_repo]):
        return

    try:
        subprocess.run(["git", "-C", base_dir, "add", os.path.relpath(history_file_path, base_dir)], check=True)
        # Check if there are staged changes to commit
        diff = subprocess.run(["git", "-C", base_dir, "diff", "--cached", "--quiet"])
        if diff.returncode != 0:
            commit_msg = f"Automated history prune ({datetime.now(ZoneInfo('UTC')).strftime('%Y-%m-%d')})"
            subprocess.run(["git", "-C", base_dir, "commit", "-m", commit_msg], check=True)
            remote_url = f"https://{github_user}:{github_token}@github.com/{github_repo}.git"
            subprocess.run(["git", "-C", base_dir, "push", remote_url, "HEAD"], check=True)
            logging.info("Git push successful.")
    except Exception as e:
        logging.error(f"Git push failed: {e}")


def main():
    # 1. Do not run if main newsbot is currently executing
    if os.path.exists(LOCKFILE):
        logging.warning("Newsbot is currently running (lockfile present). Aborting prune.")
        sys.exit(0)

    if not os.path.exists(HISTORY_FILE):
        logging.warning("history.json not found. Nothing to prune.")
        return

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception as e:
        logging.error(f"Failed to read {HISTORY_FILE}: {e}")
        return

    cutoff_date = datetime.now(ZoneInfo("UTC")) - timedelta(days=RETENTION_DAYS)
    
    initial_topic_count = len(history)
    initial_article_count = sum(len(arts) for arts in history.values())

    pruned_history = {}
    articles_removed = 0

    # 2. Filter articles by date and drop empty topics
    for topic, articles in history.items():
        valid_articles = []
        for art in articles:
            try:
                pub_dt = parsedate_to_datetime(art.get("pubDate", "")).astimezone(ZoneInfo("UTC"))
                if pub_dt > cutoff_date:
                    valid_articles.append(art)
                else:
                    articles_removed += 1
            except Exception:
                # Discard articles with invalid/corrupt dates
                articles_removed += 1

        # Only retain topic if at least one article remains
        if valid_articles:
            pruned_history[topic] = valid_articles

    topics_removed = initial_topic_count - len(pruned_history)

    # 3. Only write to disk if changes were made
    if articles_removed > 0 or topics_removed > 0:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(pruned_history, f, indent=2)

        logging.info(
            f"Pruning complete: Removed {articles_removed} article(s) and {topics_removed} empty topic(s). "
            f"Remaining: {len(pruned_history)} topic(s), {sum(len(a) for a in pruned_history.values())} article(s)."
        )

        git_push_history(HISTORY_FILE, BASE_DIR)
    else:
        logging.info("No articles older than 30 days found. history.json is unchanged.")


if __name__ == "__main__":
    main()