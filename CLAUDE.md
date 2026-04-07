# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A zero-dependency Telegram bot deployed as Python serverless functions on Vercel. Uses only the Python standard library — no `python-telegram-bot`, no `requests`. The one exception is `api/cron.py`, which uses `yfinance` and `pandas` for stock data fetching.

Two independent functions:
- **`api/webhook.py`** — echo bot, handles Telegram webhook POSTs
- **`api/cron.py`** — hourly S&P 500 drop alert, triggered via GET from cron-job.org

## Commands

```bash
# Local development
vercel dev

# Trigger cron manually
curl http://localhost:3000/cron

# Register webhook with Telegram (one-time, after deploy)
python setup_webhook.py

# Ad-hoc tests (not a test suite — just exploratory scripts)
python test_yahoo.py                          # test yfinance fetching
ALPHA_VANTAGE_KEY=xxx python test_alpha.py    # test Alpha Vantage (legacy)

# Deploy
vercel
```

## Architecture

### Vercel serverless pattern
Each file in `api/` exports a class named `handler` that extends `BaseHTTPRequestHandler`. Vercel discovers these automatically. URL rewrites in `vercel.json` map `/webhook` → `/api/webhook` and `/cron` → `/api/cron`.

### Webhook flow
Telegram POSTs updates to `/webhook`. The handler always returns HTTP 200 (even on errors) so Telegram doesn't retry. `handle_update()` dispatches on the `text` field.

### Cron flow
cron-job.org GETs `/cron` hourly. The handler flushes the 200 response header *before* doing the work (Vercel function timeout mitigation), then fetches all S&P 500 symbols in parallel batches of 100 via `ThreadPoolExecutor`, and sends a Telegram message only if any stock dropped ≥ `ALERT_THRESHOLD` (-5%).

### Stock data
`sp500.json` is a dict keyed by ticker symbol, with `name` and `sector` fields. `api/cron.py` uses `yf.download()` with `period="5d"` to get the last two closes and compute intraday change. The MultiIndex column handling in `fetch_batch_quotes` is needed because `yf.download()` returns flat columns when only one ticker is in the batch.

## Environment variables

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from BotFather |
| `CHAT_ID` | Telegram channel ID (negative number) |

Set locally in `.env` (gitignored). Add to Vercel with `vercel env add <VAR>`.

## Key constraint

Keep `requirements.txt` empty and `webhook.py` stdlib-only. The cron function uses `yfinance`/`pandas` (declared in `pyproject.toml` dependencies if needed by Vercel's uv build), but the webhook must remain zero-dependency.
