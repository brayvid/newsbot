# Digest Bot

This Python script fetches the latest RSS headlines for a list of topics and sends a nicely formatted email digest with Gmail. It uses Google News RSS feeds and can be scheduled via `cron` on any Unix-based system.

## Directory Structure
```plaintext
digest-bot/
├── digest_bot.py         # Main script
├── topics.csv            # List of topics (one per line)
├── last_seen.json        # Tracks last sent article per topic
├── logs/
│   └── digest.log        # Cron + runtime logs
```
## Setup

1. **Clone/upload the project** to your server.

2. **Modify `topics.csv` to your liking:**  
   Example:
   ```
   Apple
   AI Safety
   Climate Change
   ```


3. **Add Gmail credentials to your `~/.bash_profile`:**

   (You must [create an App Password](https://support.google.com/accounts/answer/185833) from your Gmail account settings and have 2FA enabled.)

   ```bash
   export GMAIL_USER="your_email@gmail.com"
   export GMAIL_APP_PASSWORD="your_app_password"
   export MAILTO="recipient_email@example.com"
   ```

   Then run:

   ```bash
   source ~/.bash_profile
   ```

4. **Test the script:**
   ```bash
   python3 -W ignore digest_bot.py
   ```

   You should receive your digest email within a few minutes.



## Set up Cron
To send the latest digest every day at **8:00 AM**, run:

```bash
crontab -e
```

Then add:

```bash
0 8 * * * cd ~/digest-bot && /usr/bin/env bash -c 'source ~/.bash_profile && /usr/bin/env python3 -W ignore digest_bot.py' >> ~/digest-bot/logs/digest.log 2>&1
```



## Features
- Digests only include topics with new articles
- Fully HTML-formatted clickable email
- Uses `User-Agent` headers for reliable RSS fetching
- Lockfile prevents overlapping runs

## Example Digest
🗂️ Atlantic Ocean<br>
📰 <a href="https://news.google.com/rss/articles/CBMilAFBVV95cUxQaEt5eVoyMzVuODBOb0dmUkdNSmVYSUhQRDJoVGVOOXkwYk8xdTR3LTlITXVVa01abzFGcFY2WFlkeU10R2JOY1NMNWJuNUtJZlJIcm01Z3ZZaGlMa1NsZGkxekVuU2hNVWt0VmRoVHg1RGZkenZCRzZxcE5ZZjY5OWdBWTltYkdkYWNWTXV1NnNQUmlN?oc=5">A busy hurricane season is expected. Here’s how it will be different from the last - The Washington Post</a><br>
📅 Thu, 03 Apr 2025 21:00:00 GMT

🗂️ Drones<br>
📰 <a href="https://news.google.com/rss/articles/CBMilwFBVV95cUxOdlZpV3VOdElZNjNBQUhnVDhycEthVmplYjdWZVBvZnlWaEExdWNhdzU3OXVBY3prbjFHdVFYTF9YbklpUmoydWF3R29EQUszYXdhQi1paXFCdWV0MUpZcFl3emVCdGhqVGw2RXRsZVhUOF8yV2pQZmpfNDhmLUdUSUdjSjl1S1lyamg1aS1TQXoxMF9ES2Jr?oc=5">Ukrainian drones hit Russian explosives, fiber optic factories near Moscow. - The Kyiv Independent</a><br>
📅 Sat, 05 Apr 2025 12:28:23 GMT

🗂️ Elon Musk<br>
📰 <a href="https://news.google.com/rss/articles/CBMif0FVX3lxTFBzNFJIc2JMdWhZSmtObmFTN3ZETnhFSUpMY3FPZFFjTXVPeTc4aGdKRkRYcl9zT1BUeXBXU2w3djNVUFdjaUlVNWJnYVpxd1ptUVJfQTV2SkFORFNIOXRtcVJJOGpESkw2dDZQbldJQ2JsaXZuT3pkckpGa3VRaWvSAXZBVV95cUxQRmFFSDFsTW5tQ1BNTlFHY1FJTmtVbml1amlvTURkR3BNQktCVmVScVRMamdlQ2hOdkVXeVJHRDl0eGJtUHF6YUFpelZFdFFkWXFCN0dRdjRpZndGTE4yWWpLQ3RHQjRhTWNIMmdWRFJGUDQxUFdR?oc=5">‘Hands Off!’ protesters across US rally against President Donald Trump and Elon Musk - CNN</a><br>
📅 Sun, 06 Apr 2025 02:06:00 GMT

🗂️ Research<br>
📰 <a href="https://news.google.com/rss/articles/CBMibkFVX3lxTE8tdWtROVdHa2FnWXJGOE9jUmRqd3NHMzY3XzVvTDhJOGVKMWRHdjYxUXFiQ2ptR2w5eE43eTUyeWVKeVhka2tEM2xpUWZlWFF2bnlRMXM2STVRdkh1NFQxSEVnSnEwcElGQnZfMXFn0gFHQVVfeXFMUEUwNU9KRVk2UEViWU5nellVLTJfalIwOVZrWWJXSlZyVlNjMTgzLWVjc1lqR29MQ2hJWFd2b2NXRXg1c1Fxd1E?oc=5">Top American scientists just lost their jobs. Canada is rolling out the welcome mat - CBC</a><br>
📅 Sat, 05 Apr 2025 17:44:31 GMT

🗂️ US Economy<br>
📰 <a href="https://news.google.com/rss/articles/CBMiWkFVX3lxTE1UbG5rUmFIbFBXbjgxZWhzYnJfODNvS3hVb29HN19oS1M4eU53VVp6NnRDa3hqaFlXcU9NSE5aWWg2QkE4eU5mb0hvOVdsMlpBMDYwMS1KOFhZUdIBX0FVX3lxTE1vOEFsM1ZHSVN2djRCWi0yakFGb0FGTzVZamxBOEJRc0NKaExBaFMwSW1lcjlkNEJBYTRGS09JVkpyVjJtVXdFRHVWS1lIWDZLdkhRYkNNaGtlUGVzelBR?oc=5">Trump has turned his back on the foundation of US economic might - BBC</a><br>
📅 Sat, 05 Apr 2025 23:59:04 GMT