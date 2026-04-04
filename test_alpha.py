"""Explore Alpha Vantage data. Run with: ALPHA_VANTAGE_KEY=xxx python test_alpha.py"""
import json
import os
import urllib.request

KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")
SYMBOL = "GOOG"
BASE = "https://www.alphavantage.co/query"

if not KEY:
    print("ERROR: ALPHA_VANTAGE_KEY env var not set")
    exit(1)


def fetch(params: dict) -> dict:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}?{query}&apikey={KEY}"
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def show(title: str, data: dict, max_items: int = 3):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")
    # If it's a time series, show only the first few dates
    for key, val in data.items():
        if isinstance(val, dict) and len(val) > max_items:
            print(f"{key}:")
            for i, (k2, v2) in enumerate(val.items()):
                if i >= max_items:
                    print(f"  ... ({len(val)} total entries)")
                    break
                print(f"  {k2}: {v2}")
        else:
            print(f"{key}: {val}")


# 1. Real-time quote
show("GLOBAL QUOTE (real-time price)", fetch({
    "function": "GLOBAL_QUOTE", "symbol": SYMBOL
}))

# 2. Daily prices (OHLCV)
show("TIME_SERIES_DAILY (last 3 days)", fetch({
    "function": "TIME_SERIES_DAILY", "symbol": SYMBOL, "outputsize": "compact"
}))

# 3. Simple Moving Average (SMA)
show("SMA - 20-day moving average", fetch({
    "function": "SMA", "symbol": SYMBOL,
    "interval": "daily", "time_period": "20", "series_type": "close"
}))

# 4. RSI (Relative Strength Index)
show("RSI - 14-day", fetch({
    "function": "RSI", "symbol": SYMBOL,
    "interval": "daily", "time_period": "14", "series_type": "close"
}))

# 5. MACD
show("MACD", fetch({
    "function": "MACD", "symbol": SYMBOL,
    "interval": "daily", "series_type": "close"
}))
