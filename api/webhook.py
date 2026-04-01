import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def send_message(chat_id: int, text: str) -> None:
    url = f"{TELEGRAM_API}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req)


def handle_update(update: dict) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text.startswith("/start"):
        send_message(chat_id, "Hello! I'm your Telegram bot running on Vercel.")
    elif text.startswith("/help"):
        send_message(
            chat_id,
            "Available commands:\n/start — greet\n/help — show this message\n/echo <text> — repeat your text",
        )
    elif text.startswith("/echo "):
        send_message(chat_id, text[6:])
    else:
        send_message(chat_id, f"You said: {text}")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            update = json.loads(body)
            handle_update(update)
        except Exception as e:
            print(f"Error handling update: {e}")
        # Always respond 200 so Telegram doesn't retry
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running.")

    def log_message(self, format, *args):
        pass  # suppress default access logs
