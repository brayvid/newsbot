import json
import os
from dotenv import load_dotenv
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_FROM = os.getenv("GMAIL_USER", "").encode("ascii", "ignore").decode()
EMAIL_TO = EMAIL_FROM
EMAIL_BCC = os.getenv("MAILTO", "").strip()
EMAIL_BCC_LIST = [email.strip() for email in EMAIL_BCC.split(",") if email.strip()]
SMTP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

BASE_DIR = os.path.dirname(__file__)
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")

# Initialize logging immediately to capture all runtime info
log_path = os.path.join(BASE_DIR, "logs/summary.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)
logging.basicConfig(filename=log_path, level=logging.INFO)
logging.info(f"Summary script started at {datetime.now()}")

# Load history
with open(HISTORY_FILE, "r") as f:
    history_data = json.load(f)

# Format history into a prompt
def format_history(data):
    prompt_parts = []
    for topic, articles in data.items():
        prompt_parts.append(f"### {topic.title()}")
        for article in articles:
            title = article.get("title")
            date = article.get("pubDate")
            prompt_parts.append(f"- {title} ({date})")
    return "\n".join(prompt_parts)

# Initialize Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(model_name="models/gemini-2.5-flash-preview-05-20")

# Create prompt
history_prompt = format_history(history_data)
question = "Give a brief report with short paragraphs in roughly 200 words on how the world has been doing lately based on the attached headlines. Use simple language, cite figures, and be specific with people, places, things, etc. Do not use bullet points. State the timeframe being discussed. Don't state that it's a report, simply present the findings. Then at the end, in 100 words, using all available clues in the headlines, predict what should in all likelihood occur in the near future, and less likely but still entirely possible events, and give a sense of the ramifications."
response = model.generate_content(f"{question}\n\n{history_prompt}")
answer = response.text.strip()

# Prepare email
msg = MIMEMultipart("alternative")
current_month_year = datetime.now().strftime("%B %Y")
msg["Subject"] = f"🗞️ News Review - {current_month_year}"
msg["From"] = EMAIL_FROM
msg["To"] = EMAIL_TO
msg["Bcc"] = ", ".join(EMAIL_BCC_LIST)
formatted_answer = answer.replace('\n', '<br>')
html = f"""
<html>
  <body>
    <p>{formatted_answer}</p>
  </body>
</html>
"""
part = MIMEText(html, "html")
msg.attach(part)

# Send email
try:
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_FROM, SMTP_PASS)
        server.send_message(msg)
    logging.info("News summary email sent successfully.")

except Exception as e:
    logging.error(f"Email failed: {e}")
