"""
Simpele Telegram-verstuurfunctie via de Bot API.
Vereist environment variables: TELEGRAM_TOKEN en TELEGRAM_CHAT_ID.
"""

import os
import requests


def send_telegram_message(text: str):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("WAARSCHUWING: TELEGRAM_TOKEN of TELEGRAM_CHAT_ID niet gezet - bericht niet verstuurd.")
        print("Bericht was:\n" + text)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            print(f"Telegram-fout ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"Telegram-verzendfout: {e}")


def send_telegram_photo(image_path: str, caption: str = ""):
    """
    Verstuurt een lokaal opgeslagen afbeelding (PNG) naar Telegram, met optioneel
    een bijschrift (caption). Gebruikt bij een signaal om de chart mee te sturen.
    """
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("WAARSCHUWING: TELEGRAM_TOKEN of TELEGRAM_CHAT_ID niet gezet - foto niet verstuurd.")
        return

    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    try:
        with open(image_path, "rb") as photo:
            files = {"photo": photo}
            data = {
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML",
            }
            resp = requests.post(url, data=data, files=files, timeout=30)
            if resp.status_code != 200:
                print(f"Telegram-foto-fout ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"Telegram-foto-verzendfout: {e}")
