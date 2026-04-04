# Telegram Bot on Vercel

A zero-dependency Telegram bot deployed as a Python serverless function on Vercel. Uses only the Python standard library — no `python-telegram-bot`, no `requests`.

---

## How it works

### S&P 500 drop alert (hourly cron)

```
cron-job.org (every hour)
        ↓  GET /cron
   api/cron.py
        ↓  load sp500.json (503 tickers)
        ↓  one batch request → Yahoo Finance
        ↓  filter: change% <= -5%
        ↓  send_message → Telegram channel (if any alerts)
```

### Echo bot (on-demand)

```
Telegram  →  POST /webhook  →  api/webhook.py
                                    ↓
                           handle_update() dispatches commands
                                    ↓
                           send_message() replies
```

---

## Project structure

```
.
├── api/
│   ├── cron.py          # Hourly job: check S&P 500 for ≥5% drops → alert
│   └── webhook.py       # Echo bot: handles incoming Telegram messages
├── sp500.json           # All 503 S&P 500 tickers (edit to add/remove)
├── setup_webhook.py     # One-time script to register the webhook with Telegram
├── vercel.json          # URL rewrites, no framework
├── pyproject.toml       # Python project metadata (required by Vercel uv build)
├── requirements.txt     # Empty — stdlib only
└── .env.example         # Environment variable template
```

---

## Setup & deployment

### 1. Create a Telegram bot

Talk to [@BotFather](https://t.me/BotFather) and run `/newbot`. Copy the token.

### 2. Create a Telegram channel

1. Create a new channel in Telegram (e.g. "S&P 500 Alerts")
2. Add your bot as **Admin** with the "Post Messages" permission
3. Get the channel's `CHAT_ID`:

```bash
# After adding the bot as admin, send any message to the channel, then call:
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
# Look for "chat": {"id": -100xxxxxxxxxx} — that negative number is the CHAT_ID
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Fill in TELEGRAM_TOKEN and CHAT_ID
```

In Vercel:

```bash
vercel env add TELEGRAM_TOKEN
vercel env add CHAT_ID
```

> No Alpha Vantage key needed — the cron now uses Yahoo Finance (free, no key).

### 4. Deploy to Vercel

```bash
npm i -g vercel   # install CLI if needed
vercel            # deploy
```

### 5. Set up cron-job.org

1. Sign up at [cron-job.org](https://cron-job.org)
2. Create a new cron job:
   - **URL:** `https://your-app.vercel.app/cron`
   - **Schedule:** every hour (`:00` of each hour)
   - **Method:** GET
3. Save — it will now check for stock drops every hour automatically

### 6. Register the echo bot webhook (optional)

Only needed if you also want the echo bot (`/start`, `/help`, `/echo`):

```bash
python setup_webhook.py
```

---

## Environment variables

| Variable | Description |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot token from BotFather |
| `CHAT_ID` | Telegram channel ID (negative number, e.g. `-1001234567890`) |

---

## Alert message format

Sent only when at least one stock drops ≥ 5% on the day:

```
🚨 S&P 500 Alert — 2 stock(s) down ≥5% today

📉 NVIDIA Corporation (NVDA) dropped -6.43%
💵 Price: $112.50

📉 Tesla Inc (TSLA) dropped -5.12%
💵 Price: $241.30
```

Results are sorted worst-first. No message is sent on normal days.

---

## Customisation

- **Change the threshold:** edit `ALERT_THRESHOLD = -5.0` in `api/cron.py`
- **Add/remove tickers:** edit `sp500.json` — it's a plain JSON array of symbols

---

## Rate limits

| Resource | Free limit | Usage |
|----------|-----------|-------|
| Yahoo Finance | no key / no hard limit | 1 batch req/hour ✅ |
| Vercel functions | generous free tier | 24 invocations/day ✅ |
| cron-job.org | free | unlimited ✅ |

---

## Local development

```bash
vercel dev
```

Then trigger the cron manually:

```bash
curl http://localhost:3000/cron
```
