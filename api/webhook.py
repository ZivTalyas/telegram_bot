import json
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Routes that can be triggered via bot commands
ROUTES = {
    "/reduce_5_percent": "Check top-100 S&P 500 stocks down ≥5% today and send alerts",
    "/stock_rate":       "Run fundamental screener on all S&P 500 and return top 5 per sector",
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


def run_reduce_5_percent(chat_id: int) -> None:
    send_message(chat_id, "⏳ Running /reduce_5_percent — fetching S&P 500 quotes...")
    try:
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
        send_message(chat_id, f"❌ Error: {e}")


def run_stock_rate(chat_id: int) -> None:
    send_message(chat_id, "⏳ Running /stock_rate — scanning S&P 500 fundamentals, this may take a few minutes...")
    try:
        api_dir = os.path.dirname(os.path.abspath(__file__))
        if api_dir not in sys.path:
            sys.path.insert(0, api_dir)
        from stock_rate import run_scan, _SP500_DATA  # noqa: PLC0415

        symbols = list(_SP500_DATA.keys())
        top5 = run_scan(symbols)

        if not top5:
            send_message(chat_id, "✅ Scan complete — no stocks passed the minimum score threshold.")
            return

        lines = ["📊 *S&P 500 Fundamental Screener — Top 5 per Sector*\n"]
        for sector, stocks in top5.items():
            lines.append(f"\n*{sector}*")
            for s in stocks:
                lines.append(f"  • `{s['ticker']}` {s['name']} — score {s['total_score']:.1f}/10")

        send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
    except ImportError as e:
        send_message(chat_id, f"❌ Missing dependency: {e}\n\nMake sure yfinance and pandas are installed.")
    except Exception as e:
        send_message(chat_id, f"❌ Error: {e}")


COMMAND_RUNNERS = {
    "/reduce_5_percent": run_reduce_5_percent,
    "/stock_rate":       run_stock_rate,
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
