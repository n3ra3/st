import os

import requests
from dotenv import load_dotenv


def main() -> None:
    load_dotenv(override=True)

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is missing in .env")
    if not chat_id:
        raise SystemExit("TELEGRAM_CHAT_ID is missing in .env")

    base = f"https://api.telegram.org/bot{token}"

    me = requests.get(f"{base}/getMe", timeout=20)
    if me.status_code != 200:
        print(f"getMe failed with HTTP {me.status_code}. Check TELEGRAM_BOT_TOKEN.")
        return

    me_data = me.json()
    if not me_data.get("ok"):
        print(f"getMe returned error: {me_data}")
        return

    bot_username = me_data.get("result", {}).get("username", "unknown")
    print(f"Bot token is valid. Bot username: @{bot_username}")

    payload = {
        "chat_id": chat_id,
        "text": "[SteamNote] Test message: bot can post to this chat.",
        "disable_web_page_preview": True,
    }

    send = requests.post(f"{base}/sendMessage", json=payload, timeout=20)
    if send.status_code == 200:
        body = send.json()
        if body.get("ok"):
            print("Success: test message sent.")
            return
        print(f"Telegram API returned error: {body}")
        return

    print(f"sendMessage failed with HTTP {send.status_code}.")
    try:
        error_data = send.json()
    except Exception:
        error_data = {"description": send.text[:300]}

    print(f"Details: {error_data}")

    if send.status_code in (400, 403):
        print("Hint: check TELEGRAM_CHAT_ID, chat type, and bot rights in that chat.")


if __name__ == "__main__":
    main()
