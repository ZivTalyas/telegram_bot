import http.cookiejar
import json
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_HERE, "sp500.json")) as _f:
    SP500_SYMBOLS: list = json.load(_f)

ALERT_THRESHOLD = -5.0  # percent

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_cookie_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_cookie_jar)
)


def _get_crumb() -> str:
    """Obtain a Yahoo Finance session cookie and crumb token."""
    # fc.yahoo.com is Yahoo's cookie/auth domain — more reliable than finance.yahoo.com
    # from data-center IPs (avoids the GDPR consent wall)
    _opener.open(
        urllib.request.Request(
            "https://fc.yahoo.com",
            headers={**_BROWSER_HEADERS, "Accept": "text/html,application/xhtml+xml,*/*"},
        ),
        timeout=10,
    )
    req = urllib.request.Request(
        "https://query2.finance.yahoo.com/v1/test/getcrumb",
        headers={**_BROWSER_HEADERS, "Accept": "*/*"},
    )
    with _opener.open(req, timeout=10) as resp:
        return resp.read().decode().strip()


def fetch_batch_quotes(symbols: list) -> list:
    """Fetch quotes from Yahoo Finance in batches of 100."""
    crumb = _get_crumb()
    results = []
    for i in range(0, len(symbols), 100):
        batch = ",".join(symbols[i:i + 100])
        url = (
            "https://query2.finance.yahoo.com/v8/finance/quote"
            f"?symbols={batch}&crumb={urllib.parse.quote(crumb)}"
            "&fields=symbol,shortName,regularMarketPrice,regularMarketChangePercent"
        )
        req = urllib.request.Request(
            url,
            headers={**_BROWSER_HEADERS, "Accept": "application/json"},
        )
        with _opener.open(req, timeout=10) as resp:
            data = json.loads(resp.read())
        results.extend(data.get("quoteResponse", {}).get("result", []))
    return results


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
