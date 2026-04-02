# Telegram Bot on Vercel

A zero-dependency Telegram bot deployed as a Python serverless function on Vercel. Uses only the Python standard library — no `python-telegram-bot`, no `requests`.

---

## How it works

```
Telegram  →  POST /webhook  →  Vercel serverless function (api/webhook.py)
                                        ↓
                               handle_update() parses the message
                                        ↓
                               send_message() replies via Telegram Bot API
```

- `vercel.json` rewrites `/webhook` → `/api/webhook` so Telegram's webhook URL stays clean.
- The handler always returns HTTP 200 so Telegram never retries a failed delivery.

---

## Project structure

```
.
├── api/
│   └── webhook.py       # Vercel serverless handler + bot logic
├── setup_webhook.py     # One-time script to register the webhook with Telegram
├── vercel.json          # Vercel config: URL rewrite, no framework
├── pyproject.toml       # Python project metadata (required by Vercel uv build)
├── requirements.txt     # Empty — stdlib only
└── .env.example         # Environment variable template
```

---

## Setup & deployment

### 1. Create a Telegram bot

Talk to [@BotFather](https://t.me/BotFather) on Telegram and run `/newbot`. Copy the token it gives you.

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env and set TELEGRAM_TOKEN=<your token>
```

### 3. Deploy to Vercel

```bash
# Install Vercel CLI if you haven't already
npm i -g vercel

# Deploy (first time: follow the prompts)
vercel

# Set the token as a Vercel environment variable
vercel env add TELEGRAM_TOKEN
```

### 4. Register the webhook

Run this once after each new deployment URL:

```bash
python setup_webhook.py
# Enter your token and the Vercel URL when prompted
```

---

## Commands

| Command | Response |
|---------|----------|
| `/start` | Greeting message |
| `/help` | Lists available commands |
| `/echo <text>` | Repeats `<text>` back |
| anything else | Echoes the message with "You said: " prefix |

---

## Local development

The serverless handler uses `http.server.BaseHTTPRequestHandler` which Vercel invokes directly — there is no local dev server built in. To test locally you can use [ngrok](https://ngrok.com/) to tunnel to a local HTTP server, or use the Vercel CLI:

```bash
vercel dev
```

Then point your Telegram webhook at the ngrok/Vercel dev URL using `setup_webhook.py`.

---

## Environment variables

| Variable | Description |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot token from BotFather |
