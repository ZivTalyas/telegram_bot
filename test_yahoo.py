"""Test Yahoo Finance batch quote fetching. Run with: python test_yahoo.py"""
import yfinance as yf

TEST_SYMBOLS = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOG"]


def fetch_quotes(symbols: list) -> list:
    tickers = yf.Tickers(" ".join(symbols))
    results = []
    for symbol in symbols:
        info = tickers.tickers[symbol].fast_info
        results.append({
            "symbol": symbol,
            "price": info.last_price,
            "change_pct": (info.last_price / info.previous_close - 1) * 100,
        })
    return results


def show(quotes: list):
    print(f"\n{'='*55}")
    print(f"  Results ({len(quotes)} quotes)")
    print(f"{'='*55}")
    for q in quotes:
        arrow = "📉" if q["change_pct"] < 0 else "📈"
        print(f"{arrow}  {q['symbol']:6s}  ${q['price']:>10.2f}   {q['change_pct']:+.2f}%")


if __name__ == "__main__":
    try:
        quotes = fetch_quotes(TEST_SYMBOLS)
        show(quotes)
        print("\nSUCCESS — yfinance fetch is working.")
    except Exception as e:
        print(f"\nFAILED: {e}")
