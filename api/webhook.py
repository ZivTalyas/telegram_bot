import json
import os
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

_scan_lock = threading.Lock()

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
    if not _scan_lock.acquire(blocking=False):
        send_message(chat_id, "⚠️ A scan is already running. Please wait for it to finish.")
        return
    try:
        _run_stock_rate(chat_id)
    finally:
        _scan_lock.release()


def _run_stock_rate(chat_id: int) -> None:
    send_message(chat_id, "⏳ Starting /stock_rate — scanning S&P 500 fundamentals for all companies...")
    try:
        api_dir = os.path.dirname(os.path.abspath(__file__))
        if api_dir not in sys.path:
            sys.path.insert(0, api_dir)
        from stock_rate import score_ticker, _SP500_DATA, MIN_SCORE  # noqa: PLC0415

        symbols = list(_SP500_DATA.keys())
        total = len(symbols)
        results = []
        done = 0
        last_reported = 0

        def _score(sym):
            try:
                return score_ticker(sym, _SP500_DATA.get(sym, {}))
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = {ex.submit(_score, sym): sym for sym in symbols}
            for future in as_completed(futures):
                result = future.result()
                done += 1
                pct = int(done / total * 100)
                if pct >= last_reported + 10:
                    send_message(chat_id, f"📈 {pct}% — {done}/{total} stocks scanned...")
                    last_reported = pct
                if result and result["total_score"] >= MIN_SCORE:
                    results.append(result)

        if not results:
            send_message(chat_id, "✅ Scan complete — no stocks passed the minimum score threshold.")
            return

        top10 = sorted(results, key=lambda x: x["total_score"], reverse=True)[:10]

        from datetime import date  # noqa: PLC0415
        today = date.today().strftime("%d/%m/%Y")

        lines = [
            f"📅 {today}",
            f"✅ {len(results)}/{total} stocks passed threshold — *Top 10 across all sectors:*",
            "",
        ]

        for i, s in enumerate(top10, 1):
            raw = s["raw_values"]

            data_lines = []
            if raw.get("revenue_growth") is not None:
                data_lines.append(f"Revenue Growth : {raw['revenue_growth'] * 100:+.1f}%")
            if raw.get("gross_margin") is not None:
                data_lines.append(f"Gross Margin   : {raw['gross_margin'] * 100:.1f}%")
            if raw.get("eps_growth") is not None:
                data_lines.append(f"EPS Growth     : {raw['eps_growth'] * 100:+.1f}%")
            if raw.get("ocf_growth") is not None:
                data_lines.append(f"OCF Growth     : {raw['ocf_growth'] * 100:+.1f}%")
            if raw.get("roe") is not None:
                data_lines.append(f"ROE            : {raw['roe'] * 100:.1f}%")
            if raw.get("debt_equity") is not None:
                data_lines.append(f"Debt/Equity    : {raw['debt_equity']:.2f}")
            if raw.get("forward_pe") is not None:
                data_lines.append(f"Forward P/E    : {raw['forward_pe']:.1f}x")
            if raw.get("earnings_beat") is not None:
                data_lines.append(f"Earnings Beat  : {raw['earnings_beat'] * 100:.0f}%")
            if raw.get("analyst_rev") is not None:
                data_lines.append(f"Analyst Rev.   : {str(raw['analyst_rev']).capitalize()}")

            lines.append(f"*{i}. {s['name']} ({s['ticker']})*")
            lines.append(f"Sector: {s['sector']} — Score: *{s['total_score']:.1f}/10*")
            if data_lines:
                lines.append("```")
                lines.extend(data_lines)
                lines.append("```")
            for r in s["reasons"]:
                lines.append(f"  ✓ {r}")
            for f in s["red_flags"]:
                lines.append(f"  ⚠️ {f}")
            lines.append("")

        # Telegram limit is 4096 chars — split if needed
        msg, chunk = "", "\n".join(lines)
        if len(chunk) <= 4096:
            send_message(chat_id, chunk, parse_mode="Markdown")
        else:
            current = ""
            for line in lines:
                if len(current) + len(line) + 1 > 4090:
                    send_message(chat_id, current.strip(), parse_mode="Markdown")
                    current = ""
                current += line + "\n"
            if current.strip():
                send_message(chat_id, current.strip(), parse_mode="Markdown")

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

        # Respond 200 immediately so Telegram doesn't retry
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
        self.wfile.flush()

        try:
            update = json.loads(body)
            threading.Thread(target=handle_update, args=(update,), daemon=True).start()
        except Exception as e:
            print(f"Error handling update: {e}")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running.")

    def log_message(self, format, *args):
        pass
