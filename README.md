# Telegram Bot on Vercel

A zero-dependency Telegram bot deployed as a Python serverless function on Vercel. Uses only the Python standard library — no `python-telegram-bot`, no `requests`.

---

## How it works

### Finance reporter (hourly cron)

```
cron-job.org (every hour)
        ↓  GET /cron
   api/cron.py
        ↓  fetch GLOBAL_QUOTE for GOOG from Alpha Vantage
        ↓  format message
        ↓  send_message → Telegram channel (read-only for users)
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
│   ├── cron.py          # Hourly job: fetch GOOG quote → publish to Telegram
│   └── webhook.py       # Echo bot: handles incoming Telegram messages
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

1. Create a new channel in Telegram (e.g. "GOOG Finance Feed")
2. Add your bot as **Admin** with the "Post Messages" permission
3. Get the channel's `CHAT_ID`:

```bash
# After adding the bot as admin, send any message to the channel, then call:
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
# Look for "chat": {"id": -100xxxxxxxxxx} — that negative number is the CHAT_ID
```

### 3. Get an Alpha Vantage API key

Sign up at [alphavantage.co](https://www.alphavantage.co/support/#api-key). Free tier: 25 req/day.  
At 1 request/hour = 24/day — fits within the free tier.

### 4. Configure environment variables

```bash
cp .env.example .env
# Fill in all three values
```

In Vercel:

```bash
vercel env add TELEGRAM_TOKEN
vercel env add ALPHA_VANTAGE_KEY
vercel env add CHAT_ID
```

### 5. Deploy to Vercel

```bash
npm i -g vercel   # install CLI if needed
vercel            # deploy
```

### 6. Set up cron-job.org

1. Sign up at [cron-job.org](https://cron-job.org)
2. Create a new cron job:
   - **URL:** `https://your-app.vercel.app/cron`
   - **Schedule:** every hour (`:00` of each hour)
   - **Method:** GET
3. Save — it will now trigger the hourly stock report automatically

### 7. Register the echo bot webhook (optional)

Only needed if you also want the echo bot (`/start`, `/help`, `/echo`):

```bash
python setup_webhook.py
```

---

## Environment variables

| Variable | Description |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot token from BotFather |
| `ALPHA_VANTAGE_KEY` | API key from alphavantage.co |
| `CHAT_ID` | Telegram channel ID (negative number, e.g. `-1001234567890`) |

---

## Hourly message format

```
📈 GOOG — Hourly Update
💵 Price: $174.39
🔄 Change: -1.60 (-0.9092%)
📊 High: $177.00 | Low: $173.56
📦 Volume: 21,389,847
📅 2024-01-15
```

---

## Rate limits

| Resource | Free limit | Usage at 1/hour |
|----------|-----------|-----------------|
| Alpha Vantage | 25 req/day | 24 req/day ✅ |
| Vercel functions | generous free tier | 24 invocations/day ✅ |
| cron-job.org | free | unlimited ✅ |

---

## Local development

```bash
vercel dev
```

Then use cron-job.org or `curl` to test the cron endpoint manually:

```bash
curl http://localhost:3000/cron
```
