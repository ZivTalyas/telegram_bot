import json
import os
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler

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


# ── Vercel handler ─────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    """GET /stock_rate — fundamental screener for S&P 500, returns JSON results."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.flush()

        symbols = list(_SP500_DATA.keys())
        top5    = run_scan(symbols)
        self.wfile.write(json.dumps(top5).encode("utf-8"))

    def log_message(self, format, *args):
        pass
