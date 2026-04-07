import os
from collections import OrderedDict

import requests
from dotenv import load_dotenv


def main() -> None:
    load_dotenv(override=True)

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is missing in .env")

    base = f"https://api.telegram.org/bot{token}"

    webhook = requests.get(f"{base}/getWebhookInfo", timeout=20)
    webhook.raise_for_status()
    webhook_data = webhook.json()
    if webhook_data.get("ok") and webhook_data.get("result", {}).get("url"):
        print("Webhook is enabled. Disabling webhook so getUpdates can work...")
        disable = requests.get(f"{base}/deleteWebhook", params={"drop_pending_updates": False}, timeout=20)
        disable.raise_for_status()
        print("Webhook disabled.")

    response = requests.get(f"{base}/getUpdates", timeout=30)
    response.raise_for_status()
    data = response.json()

    if not data.get("ok"):
        raise SystemExit(f"Telegram API error: {data}")

    updates = data.get("result", [])
    if not updates:
        print("No updates yet.")
        print("Send a message in your target group and run this script again.")
        print("Tip: send /id in the group and make sure bot privacy allows commands.")
        return

    chats: OrderedDict[int, dict] = OrderedDict()
    for update in updates:
        for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
            payload = update.get(key)
            if not isinstance(payload, dict):
                continue
            chat = payload.get("chat")
            if not isinstance(chat, dict):
                continue
            chat_id = chat.get("id")
            if not isinstance(chat_id, int):
                continue
            if chat_id not in chats:
                chats[chat_id] = {
                    "title": chat.get("title") or chat.get("username") or chat.get("first_name") or "unknown",
                    "type": chat.get("type", "unknown"),
                }

    if not chats:
        print("Updates found, but no chat objects parsed.")
        return

    print("Found chats:")
    for chat_id, meta in chats.items():
        print(f"- chat_id: {chat_id} | type: {meta['type']} | title: {meta['title']}")

    print("\nUse the target group chat_id value in TELEGRAM_CHAT_ID inside .env")


if __name__ == "__main__":
    main()
