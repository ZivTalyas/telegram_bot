import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler

import yfinance as yf

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_HERE, "sp500.json")) as _f:
    _SP500_DATA: dict = json.load(_f)

SP500_SYMBOLS: list = list(_SP500_DATA.keys())

ALERT_THRESHOLD = -5.0  # percent


def _fetch_one(symbol: str):
    try:
        info = yf.Ticker(symbol).fast_info
        price = info.last_price
        prev = info.previous_close
        if not price or not prev or prev == 0:
            return None
        meta = _SP500_DATA.get(symbol, {})
        return {
            "symbol": symbol,
            "name": meta.get("name", symbol),
            "sector": meta.get("sector", ""),
            "regularMarketPrice": float(price),
            "regularMarketChangePercent": float((price / prev - 1) * 100),
        }
    except Exception:
        return None


def fetch_batch_quotes(symbols: list) -> list:
    """Fetch all quotes in parallel — 50 concurrent yfinance requests."""
    with ThreadPoolExecutor(max_workers=50) as executor:
        return [r for r in executor.map(_fetch_one, symbols) if r is not None]


def format_alert(quote: dict) -> str:
    """Format a single stock alert line."""
    symbol = quote.get("symbol", "?")
    name = quote.get("name", symbol)
    sector = quote.get("sector", "")
    price = quote.get("regularMarketPrice", 0)
    change_pct = quote.get("regularMarketChangePercent", 0)
    sector_line = f"\n🏢 Sector: `{sector}`" if sector else ""
    return (
        f"📉 *{name} ({symbol})* dropped `{change_pct:.2f}%`\n"
        f"💵 Price: `${price:.2f}`{sector_line}"
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
        # Respond immediately so the cron trigger does not time out
        self.send_response(200)
        self.end_headers()
        self.wfile.flush()

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

            self.wfile.write(
                f"checked {len(quotes)} stocks, {len(alerts)} alerts sent".encode()
            )
        except Exception as e:
            print(f"Cron error: {e}")
            self.wfile.write(str(e).encode())

    def log_message(self, format, *args):
        """Suppress default per-request access logs."""
        pass
