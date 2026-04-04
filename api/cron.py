import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_HERE, "sp500.json")) as _f:
    SP500_SYMBOLS: list = json.load(_f)

ALERT_THRESHOLD = -5.0  # percent


def fetch_batch_quotes(symbols: list) -> list:
    """Fetch batch quotes from Yahoo Finance (no API key required)."""
    joined = ",".join(symbols)
    url = (
        "https://query1.finance.yahoo.com/v7/finance/quote"
        f"?symbols={joined}"
        "&fields=symbol,shortName,regularMarketPrice,regularMarketChangePercent"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data.get("quoteResponse", {}).get("result", [])


def format_alert(quote: dict) -> str:
    """Format a single stock alert line."""
    symbol = quote.get("symbol", "?")
    name = quote.get("shortName", symbol)
    price = quote.get("regularMarketPrice", 0)
    change_pct = quote.get("regularMarketChangePercent", 0)
    return (
        f"📉 *{name} ({symbol})* dropped `{change_pct:.2f}%`\n"
        f"💵 Price: `${price:.2f}`"
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
    """Vercel serverless cron — checks S&P 500 stocks for drops ≥5% today."""

    def do_GET(self):
        try:
            quotes = fetch_batch_quotes(SP500_SYMBOLS)
            alerts = sorted(
                [q for q in quotes if q.get("regularMarketChangePercent", 0) <= ALERT_THRESHOLD],
                key=lambda q: q.get("regularMarketChangePercent", 0),
            )

            if alerts:
                header = f"🚨 *S&P 500 Alert — {len(alerts)} stock(s) down ≥5% today*\n\n"
                body = "\n\n".join(format_alert(q) for q in alerts)
                send_message(CHAT_ID, header + body)

            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                f"checked {len(quotes)} stocks, {len(alerts)} alerts sent".encode()
            )
        except Exception as e:
            print(f"Cron error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, format, *args):
        """Suppress default per-request access logs."""
        pass
