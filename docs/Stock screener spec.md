# Stock Growth Screener — Logic Specification

## What We're Building

A stock screener that evaluates companies using **9 fundamental parameters** across 3 groups,
assigns a color-coded score to each, and outputs a report of the **Top 5 companies per sector**
with written reasons explaining why each was selected.

Two features:
- **Feature 1 — Single ticker**: input one stock symbol → get score + breakdown
- **Feature 2 — Batch scan**: input a CSV/Excel file with a list of tickers → get a full HTML report

---

## The 9 Parameters & Their Groups

| # | Parameter | Group |
|---|-----------|-------|
| 1 | Revenue Growth YoY | Growth |
| 2 | Gross Margin | Growth |
| 3 | EPS Growth | Growth |
| 4 | Operating Cash Flow Growth | Efficiency |
| 5 | Return on Equity (ROE) | Efficiency |
| 6 | Debt-to-Equity | Efficiency |
| 7 | Forward P/E | Future Potential |
| 8 | Earnings Beat % | Future Potential |
| 9 | Analyst Revision | Future Potential |

---

## Scoring Thresholds

### Standard parameters

| Parameter | Green (strong) | Yellow (ok) | Red (flag) | Note |
|-----------|---------------|-------------|------------|------|
| revenue_growth | > 15% | 8–15% | < 8% | |
| eps_growth | > 20% | 10–20% | < 10% | |
| ocf_growth | > 10% | 0–10% | negative | |
| roe | > 20% | 15–20% | < 15% | |
| forward_pe | < 20 | 20–35 | > 35 | **inverted** — lower is better |
| earnings_beat | > 75% | 50–75% | < 50% | % of quarters beat |
| analyst_rev | "up" | "neutral" | "down" | direction of estimate changes |

### Sector-dependent: Gross Margin

| Sector | Green | Yellow | Red |
|--------|-------|--------|-----|
| Technology, Communication Services | > 60% | 40–60% | < 40% |
| All other sectors | > 35% | 20–35% | < 20% |

### Sector-dependent: Debt-to-Equity

| Sector | Green | Yellow | Red |
|--------|-------|--------|-----|
| Financial Services, Real Estate, Utilities | < 3.0 | 3–5 | > 5 |
| All other sectors | < 0.5 | 0.5–1.5 | > 2.0 |

---

## Scoring Logic

### Step 1 — Classify each parameter

```
for each parameter:
  if value is None or unavailable → "na"  (excluded from score)
  
  if not inverted:
    value >= green_threshold  → "green"
    value >= yellow_threshold → "yellow"
    else                      → "red"
    
  if inverted (forward_pe):
    value <= green_threshold  → "green"
    value <= yellow_threshold → "yellow"
    else                      → "red"
```

### Step 2 — Weighted total score (0–10)

```python
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

# Only include parameters that are not "na"
weighted_sum = sum(SCORE_MAP[status] * WEIGHTS[param]
                   for param, status in scores.items()
                   if status != "na")

active_weight = sum(WEIGHTS[param]
                    for param, status in scores.items()
                    if status != "na")

total_score = (weighted_sum / active_weight) if active_weight > 0 else 0.0
# Result: float between 0.0 and 10.0
```

### Step 3 — Generate reason sentences

For every **green** parameter, generate a plain-language reason string.
For every **red** parameter, generate a red flag string.

Templates:

```
GREEN reasons:
  revenue_growth = 0.28  → "Revenue growth of 28% year-over-year"
  gross_margin   = 0.74  → "Gross margin of 74%"
  eps_growth     = 0.35  → "EPS growth of 35% year-over-year"
  ocf_growth     = 0.15  → "Operating cash flow grew 15%"
  roe            = 0.24  → "ROE of 24%, above the 20% threshold"
  debt_equity    = 0.3   → "Low leverage — Debt/Equity of 0.30"
  forward_pe     = 18    → "Attractive forward P/E of 18"
  earnings_beat  = 0.75  → "Beat estimates in 3 of the last 4 quarters"
  analyst_rev    = "up"  → "Analysts are raising price targets"

RED flags:
  revenue_growth = 0.04  → "Weak revenue growth of only 4%"
  debt_equity    = 2.8   → "High leverage — Debt/Equity of 2.80"
  forward_pe     = 55    → "Expensive valuation — forward P/E of 55"
  roe            = 0.08  → "Low ROE of 8%, below the 15% threshold"
  ocf_growth     negative → "Negative operating cash flow growth"
```

### Step 4 — Score object returned per ticker

```python
{
    "ticker":      "NVDA",
    "name":        "NVIDIA Corporation",
    "sector":      "Technology",
    "scores": {
        "revenue_growth": "green",
        "gross_margin":   "green",
        "eps_growth":     "green",
        "ocf_growth":     "yellow",
        "roe":            "green",
        "debt_equity":    "green",
        "forward_pe":     "red",
        "earnings_beat":  "green",
        "analyst_rev":    "green",
    },
    "raw_values": {
        "revenue_growth": 0.28,
        "gross_margin":   0.74,
        # ... actual numbers for display
    },
    "total_score":  7.6,
    "green_count":  7,
    "red_count":    1,
    "reasons":      ["Revenue growth of 28% year-over-year", ...],
    "red_flags":    ["Expensive valuation — forward P/E of 55"],
}
```

---

## Top 5 Per Sector — Filter Logic

```
After all tickers are scored:

1. EXCLUDE any ticker where total_score < 4.0
   (not worth including even as last in sector)

2. Group remaining tickers by sector

3. Within each sector:
   - Sort by total_score descending
   - Take top 5 only

4. If a sector has zero tickers above 4.0:
   - Still include the sector in the report
   - Show message: "No companies met the minimum threshold in this sector"

5. Final output: dict keyed by sector → list of up to 5 scored ticker objects
```

---

## Report Content — What to Show Per Company

For each of the Top 5 in each sector, the report must include:

```
[Company Name] ([TICKER])          Score: 8.2 / 10
Sector: Technology
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Parameter          Value      Status
─────────────────────────────────────────────
Revenue Growth     +28%       ✓ Strong
Gross Margin       74%        ✓ Strong
EPS Growth         +35%       ✓ Strong
Op. Cash Flow      +15%       ~ Moderate
ROE                24%        ✓ Strong
Debt / Equity      0.30       ✓ Strong
Forward P/E        55x        ✗ High
Earnings Beat      75%        ✓ Strong
Analyst Revision   Up         ✓ Positive
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Why selected:
  • Revenue growth of 28% year-over-year
  • Gross margin of 74%
  • ROE of 24%, above the 20% threshold
  • Beat estimates in 3 of the last 4 quarters
  • Analysts are raising price targets

Red flags:
  • Expensive valuation — forward P/E of 55
```

---

## Report Structure (overall)

```
Header
  - Title, generation date
  - Summary: X tickers scanned, Y passed threshold, Z sectors covered

For each sector (sorted alphabetically):
  Sector name + count of companies shown
  Company cards 1–5 (ranked by score, highest first)

Footer
  - Disclaimer: for personal/research use only
```

---

## Error Handling Rules

- If a ticker is not found in yfinance → skip it, log a warning, continue
- If a specific parameter fails to fetch → set to `None`, mark as `"na"` in scores
- If **all 9 parameters** are `None` for a ticker → skip entirely, don't include in report
- Add a small delay between batch API calls (`sleep(0.5)`) to avoid rate limiting
- Wrap every individual parameter fetch in its own `try/except` — one failure must not affect others

---

## Input File Format (batch mode)

CSV with at minimum one column: `ticker`

The `sector` column is **optional** — if missing, fetch it from `yfinance` via `ticker.info['sector']`

```csv
ticker,sector
AAPL,Technology
MSFT,Technology
JPM,Financial Services
JNJ,Healthcare
```

---

## Summary of What Needs to Be Implemented

1. **Threshold definitions** — the green/yellow/red cutoffs per parameter, with sector overrides for gross_margin and debt_equity
2. **Parameter classifier** — takes a value + parameter name + sector → returns "green" / "yellow" / "red" / "na"
3. **Weighted score calculator** — takes all 9 classified values → returns float 0.0–10.0
4. **Reason generator** — takes scored parameters + raw values → returns list of reason strings and red flag strings
5. **Top-N sector filter** — takes list of scored tickers → groups by sector, filters by min score, returns top 5 per sector
6. **Report renderer** — takes the grouped top-5 data → outputs readable report (HTML or console table)
