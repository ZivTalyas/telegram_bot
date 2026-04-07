import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import yfinance as yf

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_HERE, "sp500.json")) as _f:
    _SP500_DATA: dict = json.load(_f)

# ── Weights & scoring ──────────────────────────────────────────────────────────

WEIGHTS = {
    "revenue_growth": 2.0,
    "gross_margin":   1.5,
    "eps_growth":     1.5,
    "ocf_growth":     1.5,
    "roe":            1.0,
    "debt_equity":    1.0,
    "forward_pe":     0.75,
    "earnings_beat":  0.75,
    "analyst_rev":    0.5,
}

SCORE_MAP = {"green": 10, "yellow": 5, "red": 0}

# ── Thresholds ─────────────────────────────────────────────────────────────────

_STANDARD = {
    "revenue_growth": {"green": 0.15, "yellow": 0.08, "inverted": False},
    "eps_growth":     {"green": 0.20, "yellow": 0.10, "inverted": False},
    "ocf_growth":     {"green": 0.10, "yellow": 0.00, "inverted": False},
    "roe":            {"green": 0.20, "yellow": 0.15, "inverted": False},
    "forward_pe":     {"green": 20,   "yellow": 35,   "inverted": True},
    "earnings_beat":  {"green": 0.75, "yellow": 0.50, "inverted": False},
}

_HIGH_MARGIN_SECTORS   = {"Technology", "Communication Services"}
_HIGH_LEVERAGE_SECTORS = {"Financial Services", "Real Estate", "Utilities"}


def _cmp(value: float, green, yellow, inverted: bool) -> str:
    if inverted:
        if value <= green:  return "green"
        if value <= yellow: return "yellow"
        return "red"
    else:
        if value >= green:  return "green"
        if value >= yellow: return "yellow"
        return "red"


def classify(param: str, value, sector: str) -> str:
    if value is None:
        return "na"

    if param == "analyst_rev":
        v = str(value).lower()
        return {"up": "green", "neutral": "yellow", "down": "red"}.get(v, "na")

    try:
        fval = float(value)
    except (TypeError, ValueError):
        return "na"

    if param == "gross_margin":
        if sector in _HIGH_MARGIN_SECTORS:
            return _cmp(fval, 0.60, 0.40, False)
        return _cmp(fval, 0.35, 0.20, False)

    if param == "debt_equity":
        if sector in _HIGH_LEVERAGE_SECTORS:
            return _cmp(fval, 3.0, 5.0, True)
        return _cmp(fval, 0.5, 1.5, True)

    t = _STANDARD.get(param)
    if not t:
        return "na"
    return _cmp(fval, t["green"], t["yellow"], t["inverted"])


# ── Reason generator ───────────────────────────────────────────────────────────

def _pct(v, signed=False) -> str:
    return f"{v * 100:+.0f}%" if signed else f"{v * 100:.0f}%"


def build_reasons(scores: dict, raw: dict) -> tuple:
    reasons, flags = [], []

    def _add(param, green_msg, red_msg):
        s = scores.get(param, "na")
        if s == "green" and green_msg:
            reasons.append(green_msg)
        elif s == "red" and red_msg:
            flags.append(red_msg)

    rv = raw.get("revenue_growth")
    _add("revenue_growth",
         f"Revenue growth of {_pct(rv, signed=True)} year-over-year" if rv is not None else None,
         f"Weak revenue growth of only {_pct(rv)}" if rv is not None else None)

    gm = raw.get("gross_margin")
    _add("gross_margin",
         f"Gross margin of {_pct(gm)}" if gm is not None else None,
         f"Thin gross margin of {_pct(gm)}" if gm is not None else None)

    eg = raw.get("eps_growth")
    _add("eps_growth",
         f"EPS growth of {_pct(eg, signed=True)} year-over-year" if eg is not None else None,
         f"Weak EPS growth of {_pct(eg)}" if eg is not None else None)

    ocf = raw.get("ocf_growth")
    _add("ocf_growth",
         f"Operating cash flow grew {_pct(ocf, signed=True)}" if ocf is not None else None,
         ("Negative operating cash flow growth" if ocf is not None and ocf < 0 else "Weak operating cash flow growth"))

    roe = raw.get("roe")
    _add("roe",
         f"ROE of {_pct(roe)}, above the 20% threshold" if roe is not None else None,
         f"Low ROE of {_pct(roe)}, below the 15% threshold" if roe is not None else None)

    de = raw.get("debt_equity")
    _add("debt_equity",
         f"Low leverage — Debt/Equity of {de:.2f}" if de is not None else None,
         f"High leverage — Debt/Equity of {de:.2f}" if de is not None else None)

    fpe = raw.get("forward_pe")
    _add("forward_pe",
         f"Attractive forward P/E of {fpe:.1f}" if fpe is not None else None,
         f"Expensive valuation — forward P/E of {fpe:.1f}" if fpe is not None else None)

    eb = raw.get("earnings_beat")
    _add("earnings_beat",
         f"Beat estimates in {round(eb * 4)} of the last 4 quarters" if eb is not None else None,
         "Missed earnings estimates frequently")

    _add("analyst_rev",
         "Analysts are raising price targets",
         "Analysts are cutting price targets")

    return reasons, flags


# ── Fetch fundamentals per ticker ──────────────────────────────────────────────

def _rec_to_direction(rec: str):
    rec = rec.lower()
    if rec in ("buy", "strong_buy"):                    return "up"
    if rec in ("hold", "neutral"):                      return "neutral"
    if rec in ("sell", "underperform", "strong_sell"):  return "down"
    return None


def fetch_fundamentals(ticker: str) -> dict | None:
    raw = {k: None for k in WEIGHTS}
    try:
        t    = yf.Ticker(ticker)
        info = t.info

        if not info or len(info) < 5:
            return None

        raw["revenue_growth"] = info.get("revenueGrowth")
        raw["gross_margin"]   = info.get("grossMargins")
        raw["eps_growth"]     = info.get("earningsGrowth")
        raw["roe"]            = info.get("returnOnEquity")
        raw["forward_pe"]     = info.get("forwardPE")

        de = info.get("debtToEquity")
        raw["debt_equity"] = de / 100 if de is not None else None

        raw["analyst_rev"] = _rec_to_direction(info.get("recommendationKey") or "")

        # OCF growth — from annual cashflow dataframe
        try:
            cf = t.cashflow
            if cf is not None and not cf.empty:
                for label in ("Operating Cash Flow", "Total Cash From Operating Activities"):
                    if label in cf.index:
                        row = cf.loc[label].dropna()
                        if len(row) >= 2:
                            curr, prev = float(row.iloc[0]), float(row.iloc[1])
                            if prev != 0:
                                raw["ocf_growth"] = (curr - prev) / abs(prev)
                        break
        except Exception:
            pass

        # Earnings beat — fraction of positive surprises over last 8 reported quarters
        try:
            ed = t.earnings_dates
            if ed is not None and not ed.empty:
                col = next((c for c in ed.columns if "Surprise" in c), None)
                if col:
                    surprises = ed[col].dropna().head(8)
                    if len(surprises) >= 2:
                        raw["earnings_beat"] = float((surprises > 0).mean())
        except Exception:
            pass

    except Exception:
        pass

    if all(v is None for v in raw.values()):
        return None

    return raw


# ── Score a single ticker ──────────────────────────────────────────────────────

def score_ticker(ticker: str, meta: dict) -> dict | None:
    name   = meta.get("name", ticker)
    sector = meta.get("sector", "")

    raw = fetch_fundamentals(ticker)
    if raw is None:
        return None

    scores = {param: classify(param, raw[param], sector) for param in WEIGHTS}

    active = {p: s for p, s in scores.items() if s != "na"}
    if not active:
        return None

    weighted_sum  = sum(SCORE_MAP[s] * WEIGHTS[p] for p, s in active.items())
    active_weight = sum(WEIGHTS[p] for p in active)
    total_score   = weighted_sum / active_weight if active_weight else 0.0

    reasons, red_flags = build_reasons(scores, raw)

    return {
        "ticker":      ticker,
        "name":        name,
        "sector":      sector,
        "scores":      scores,
        "raw_values":  raw,
        "total_score": round(total_score, 2),
        "green_count": sum(1 for s in scores.values() if s == "green"),
        "red_count":   sum(1 for s in scores.values() if s == "red"),
        "reasons":     reasons,
        "red_flags":   red_flags,
    }


# ── Batch scan ─────────────────────────────────────────────────────────────────

MIN_SCORE = 4.0
TOP_N     = 5
_WORKERS  = 20


def run_scan(symbols: list) -> dict:
    results = []

    def _score(sym):
        try:
            return score_ticker(sym, _SP500_DATA.get(sym, {}))
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=_WORKERS) as ex:
        for result in ex.map(_score, symbols):
            if result and result["total_score"] >= MIN_SCORE:
                results.append(result)

    sectors: dict = {}
    for r in results:
        sectors.setdefault(r["sector"] or "Unknown", []).append(r)

    return {
        sec: sorted(stocks, key=lambda x: x["total_score"], reverse=True)[:TOP_N]
        for sec, stocks in sorted(sectors.items())
    }


# ── HTML rendering ─────────────────────────────────────────────────────────────

_STATUS_ICON  = {"green": "✓", "yellow": "~", "red": "✗", "na": "—"}
_STATUS_LABEL = {"green": "Strong", "yellow": "Moderate", "red": "Weak", "na": "N/A"}
_STATUS_COLOR = {"green": "#16a34a", "yellow": "#ca8a04", "red": "#dc2626", "na": "#9ca3af"}

_PARAM_LABELS = {
    "revenue_growth": "Revenue Growth",
    "gross_margin":   "Gross Margin",
    "eps_growth":     "EPS Growth",
    "ocf_growth":     "Op. Cash Flow",
    "roe":            "ROE",
    "debt_equity":    "Debt / Equity",
    "forward_pe":     "Forward P/E",
    "earnings_beat":  "Earnings Beat",
    "analyst_rev":    "Analyst Rev.",
}


def _fmt(param: str, value) -> str:
    if value is None:
        return "—"
    if param == "analyst_rev":
        return str(value).capitalize()
    if param == "forward_pe":
        return f"{value:.1f}x"
    if param == "debt_equity":
        return f"{value:.2f}"
    if param in ("revenue_growth", "eps_growth", "ocf_growth"):
        return f"{value * 100:+.1f}%"
    if param in ("gross_margin", "roe", "earnings_beat"):
        return f"{value * 100:.1f}%"
    return str(value)


def _card(stock: dict) -> str:
    score  = stock["total_score"]
    scores = stock["scores"]
    raw    = stock["raw_values"]

    score_color = "#16a34a" if score >= 7 else "#ca8a04" if score >= 5 else "#dc2626"

    rows = "".join(
        f"<tr>"
        f"<td>{label}</td>"
        f"<td>{_fmt(param, raw.get(param))}</td>"
        f"<td style='color:{_STATUS_COLOR[scores.get(param,'na')]};font-weight:600'>"
        f"{_STATUS_ICON[scores.get(param,'na')]} {_STATUS_LABEL[scores.get(param,'na')]}</td>"
        f"</tr>"
        for param, label in _PARAM_LABELS.items()
    )

    reasons_html = "".join(f"<li>{r}</li>" for r in stock["reasons"])
    flags_html   = "".join(f"<li>{r}</li>" for r in stock["red_flags"])

    reasons_block = f"<div class='reasons'><b>Why selected:</b><ul>{reasons_html}</ul></div>" if reasons_html else ""
    flags_block   = f"<div class='flags'><b>Red flags:</b><ul>{flags_html}</ul></div>" if flags_html else ""

    return (
        f"<div class='card'>"
        f"<div class='card-header'>"
        f"<span class='cname'>{stock['name']} ({stock['ticker']})</span>"
        f"<span class='cscore' style='color:{score_color}'>{score:.1f} / 10</span>"
        f"</div>"
        f"<table class='ptable'><tr><th>Parameter</th><th>Value</th><th>Status</th></tr>{rows}</table>"
        f"{reasons_block}{flags_block}"
        f"</div>"
    )


def render_html(top5: dict, total_scanned: int) -> str:
    passed  = sum(len(v) for v in top5.values())
    today   = date.today().isoformat()

    sector_html = "".join(
        f"<section>"
        f"<h2>{sec} <span class='cnt'>({len(stocks)} companies)</span></h2>"
        + "".join(_card(s) for s in stocks)
        + "</section>"
        for sec, stocks in top5.items()
    )

    if not sector_html:
        sector_html = "<p>No stocks passed the minimum score threshold.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>S&P 500 Screener — {today}</title>
<style>
  body{{font-family:system-ui,sans-serif;max-width:900px;margin:40px auto;padding:0 20px;background:#f9fafb;color:#111}}
  h1{{font-size:1.8rem;margin-bottom:4px}}
  .meta{{color:#6b7280;font-size:.9rem;margin-bottom:32px}}
  h2{{font-size:1.25rem;border-bottom:2px solid #e5e7eb;padding-bottom:6px;margin-top:36px}}
  .cnt{{font-size:.85rem;color:#9ca3af;font-weight:400}}
  .card{{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:20px;margin-bottom:16px}}
  .card-header{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px}}
  .cname{{font-size:1.05rem;font-weight:700}}
  .cscore{{font-size:1.15rem;font-weight:700}}
  .ptable{{width:100%;border-collapse:collapse;font-size:.88rem}}
  .ptable th{{text-align:left;color:#6b7280;border-bottom:1px solid #e5e7eb;padding:4px 8px}}
  .ptable td{{padding:4px 8px;border-bottom:1px solid #f3f4f6}}
  .reasons{{margin-top:14px;font-size:.88rem}}
  .reasons ul{{margin:4px 0 0 16px;color:#15803d}}
  .flags{{margin-top:8px;font-size:.88rem}}
  .flags ul{{margin:4px 0 0 16px;color:#b91c1c}}
  footer{{margin-top:48px;padding-top:16px;border-top:1px solid #e5e7eb;font-size:.8rem;color:#9ca3af}}
</style>
</head>
<body>
<h1>S&amp;P 500 Stock Screener</h1>
<p class="meta">
  Generated: {today} &nbsp;|&nbsp;
  {total_scanned} tickers scanned &nbsp;|&nbsp;
  {passed} passed threshold &nbsp;|&nbsp;
  {len(top5)} sectors covered
</p>
{sector_html}
<footer>For personal and research use only. Not financial advice.</footer>
</body>
</html>"""


# ── Vercel handler ─────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    """GET /screener — fundamental screener for S&P 500, returns HTML report.

    Optional query param: ?tickers=AAPL,MSFT  (subset for quick testing)
    """

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        if "tickers" in qs:
            symbols = [t.strip().upper() for t in qs["tickers"][0].split(",") if t.strip()]
        else:
            symbols = list(_SP500_DATA.keys())

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.flush()

        top5 = run_scan(symbols)
        html = render_html(top5, len(symbols))
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass
