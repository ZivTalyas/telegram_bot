import json
import os
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_HERE, "sp500.json")) as _f:
    _SP500_DATA: dict = json.load(_f)

SP500_SYMBOLS: list = list(_SP500_DATA.keys())

ALERT_THRESHOLD = -5.0  # percent

_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _yahoo_opener():
    """Build an opener with Yahoo Finance session cookies and return (opener, crumb)."""
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = list(_HEADERS.items())
    opener.open("https://finance.yahoo.com/").close()
    crumb = opener.open(
        "https://query1.finance.yahoo.com/v1/test/getcrumb"
    ).read().decode()
    return opener, crumb


def fetch_batch_quotes(symbols: list) -> list:
    """Fetch all quotes via Yahoo Finance bulk API — ~3 requests for 500 symbols."""
    opener, crumb = _yahoo_opener()
    results = []
    for i in range(0, len(symbols), 200):
        batch = ",".join(symbols[i:i + 200])
        url = (
            "https://query1.finance.yahoo.com/v7/finance/quote"
            f"?crumb={urllib.parse.quote(crumb)}&symbols={batch}"
        )
        data = json.loads(opener.open(url).read())
        for q in data.get("quoteResponse", {}).get("result", []):
            sym = q.get("symbol")
            price = q.get("regularMarketPrice")
            change_pct = q.get("regularMarketChangePercent")
            if sym is None or price is None or change_pct is None:
                continue
            meta = _SP500_DATA.get(sym, {})
            results.append({
                "symbol": sym,
                "name": meta.get("name", sym),
                "sector": meta.get("sector", ""),
                "regularMarketPrice": price,
                "regularMarketChangePercent": change_pct,
            })
    return results


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
