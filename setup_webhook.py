"""Run this once after deploying to Vercel to register the webhook with Telegram."""
import sys
import urllib.request
import urllib.parse
import json
import os

TOKEN = os.environ.get("TELEGRAM_TOKEN") or input("Enter your TELEGRAM_TOKEN: ").strip()
VERCEL_URL = input("Enter your Vercel deployment URL (e.g. https://your-bot.vercel.app): ").strip()
WEBHOOK_URL = f"{VERCEL_URL}/webhook"

url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
data = json.dumps({"url": WEBHOOK_URL}).encode()
req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read())
    if result.get("ok"):
        print(f"Webhook set successfully: {WEBHOOK_URL}")
    else:
        print(f"Failed: {result}")
        sys.exit(1)
