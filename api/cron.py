import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
ALPHA_VANTAGE_API = "https://www.alphavantage.co/query"


def fetch_quote(symbol: str) -> dict:
    """Fetch a real-time stock quote from Alpha Vantage for the given symbol."""
    url = (
        f"{ALPHA_VANTAGE_API}"
        f"?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_VANTAGE_KEY}"
    )
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    return data.get("Global Quote", {})


def format_quote(quote: dict) -> str:
    """Format a raw Alpha Vantage quote dict into a readable Telegram message."""
    symbol = quote.get("01. symbol", "?")
    price = quote.get("05. price", "N/A")
    change = quote.get("09. change", "0")
    change_pct = quote.get("10. change percent", "N/A")
    high = quote.get("03. high", "N/A")
    low = quote.get("04. low", "N/A")
    volume = quote.get("06. volume", "N/A")
    trading_day = quote.get("07. latest trading day", "N/A")

    try:
        arrow = "📈" if float(change) >= 0 else "📉"
    except ValueError:
        arrow = "📊"

    # Format volume with thousands separator for readability
    try:
        volume_fmt = f"{int(volume):,}"
    except ValueError:
        volume_fmt = volume

    return (
        f"{arrow} *{symbol} — Hourly Update*\n"
        f"💵 Price: `${float(price):.2f}`\n"
        f"🔄 Change: `{float(change):+.2f}` ({change_pct})\n"
        f"📊 High: `${float(high):.2f}` | Low: `${float(low):.2f}`\n"
        f"📦 Volume: `{volume_fmt}`\n"
        f"📅 {trading_day}"
    )


def send_message(chat_id: str, text: str) -> None:
    """Send a Markdown-formatted message to a Telegram chat or channel."""
    url = f"{TELEGRAM_API}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req)


class handler(BaseHTTPRequestHandler):
    """Vercel serverless entry point — triggered every hour by cron-job.org."""

    def do_GET(self):
        """Fetch GOOG quote and publish it to the configured Telegram chat."""
        try:
            quote = fetch_quote("GOOG")
            if not quote:
                raise ValueError("Empty quote returned from Alpha Vantage")
            message = format_quote(quote)
            send_message(CHAT_ID, message)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        except Exception as e:
            print(f"Cron error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, format, *args):
        """Suppress default per-request access logs."""
        pass
