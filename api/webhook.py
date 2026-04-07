import json
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Routes that can be triggered via bot commands
ROUTES = {
    "/cron": "Check S&P 500 for stocks down ≥5% today and send alerts",
}


def send_message(chat_id: int, text: str, parse_mode: str = "") -> None:
    url = f"{TELEGRAM_API}/sendMessage"
    payload: dict = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req)


def run_cron(chat_id: int) -> None:
    send_message(chat_id, "⏳ Running /cron — fetching S&P 500 quotes...")
    try:
        # Add api/ dir to path so we can import sibling module
        api_dir = os.path.dirname(os.path.abspath(__file__))
        if api_dir not in sys.path:
            sys.path.insert(0, api_dir)
        from reduce_5_percent import fetch_batch_quotes, format_alert, SP500_SYMBOLS, ALERT_THRESHOLD  # noqa: PLC0415

        quotes = fetch_batch_quotes(SP500_SYMBOLS)
        alerts = sorted(
            [q for q in quotes if q.get("regularMarketChangePercent", 0) <= ALERT_THRESHOLD],
            key=lambda q: q.get("regularMarketChangePercent", 0),
        )

        if alerts:
            header = f"🚨 *S&P 500 Alert — {len(alerts)} stock(s) down ≥5% today*\n\n"
            body = "\n\n".join(format_alert(q) for q in alerts)
            send_message(chat_id, header + body, parse_mode="Markdown")
        else:
            send_message(
                chat_id,
                f"✅ Checked {len(quotes)} stocks — no drops ≥5% today.",
            )
    except ImportError as e:
        send_message(chat_id, f"❌ Missing dependency: {e}\n\nMake sure yfinance and pandas are installed.")
    except Exception as e:
        send_message(chat_id, f"❌ Cron error: {e}")


COMMAND_RUNNERS = {
    "/cron": run_cron,
}


def handle_update(update: dict) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text.startswith("/start"):
        lines = ["👋 *Bot Runner* — available commands:\n"]
        for route, description in ROUTES.items():
            lines.append(f"• `{route}` — {description}")
        lines.append("\n`/help` — show this message")
        send_message(chat_id, "\n".join(lines), parse_mode="Markdown")

    elif text.startswith("/help"):
        lines = ["*Available commands:*\n"]
        for route, description in ROUTES.items():
            lines.append(f"• `{route}` — {description}")
        lines.append("• `/help` — show this message")
        send_message(chat_id, "\n".join(lines), parse_mode="Markdown")

    else:
        # Check if the message matches a runnable route
        command = text.split()[0] if text else ""
        if command in COMMAND_RUNNERS:
            COMMAND_RUNNERS[command](chat_id)
        else:
            send_message(chat_id, f"Unknown command: `{text}`\n\nSend /start to see available commands.", parse_mode="Markdown")


class handler(BaseHTTPRequestHandler):
    """Vercel serverless entry point. Class must be named 'handler'."""

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            update = json.loads(body)
            handle_update(update)
        except Exception as e:
            print(f"Error handling update: {e}")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running.")

    def log_message(self, format, *args):
        pass
