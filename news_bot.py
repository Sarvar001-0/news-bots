#!/usr/bin/env python3
"""
Dunyo yangiliklari boti — RSS manbalardan yangiliklarni olib,
Telegram kanaliga jo'natadi. Har ishga tushganda faqat oldin
jo'natilmagan (yangi) xabarlarni tanlaydi.
"""

import os
import json
import time
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from deep_translator import GoogleTranslator

# ---------- SOZLAMALAR ----------

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]

MAX_ITEMS_PER_SOURCE = 4
LOOKBACK_HOURS = 3
POSTED_FILE = "posted_ids.json"

FEEDS = {
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Reuters World": "https://www.reutersagency.com/feed/?best-topics=world&post_type=best",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "AP News": "https://apnews.com/apf-topnews.rss",
    "NPR World": "https://feeds.npr.org/1004/rss.xml",
}

def load_posted_ids():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_posted_ids(ids):
    trimmed = list(ids)[-1000:]
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def translate_to_uzbek(text):
    try:
        return GoogleTranslator(source="auto", target="uz").translate(text)
    except Exception as e:
        print(f"[OGOHLANTIRISH] Tarjima qilinmadi, asl matn qoldirildi: {e}")
        return text


def entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    return None


def fetch_new_items(posted_ids):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    items_by_source = {}

    for source_name, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"[OGOHLANTIRISH] {source_name} manbasini o'qib bo'lmadi: {e}")
            continue

        fresh = []
        for entry in feed.entries:
            link = entry.get("link")
            if not link or link in posted_ids:
                continue

            pub_time = entry_time(entry)
            if pub_time and pub_time < cutoff:
                continue

            title = entry.get("title", "").strip()
            if not title:
                continue

            title_uz = translate_to_uzbek(title)

            fresh.append({"title": title_uz, "link": link})
            if len(fresh) >= MAX_ITEMS_PER_SOURCE:
                break

        if fresh:
            items_by_source[source_name] = fresh

    return items_by_source


def build_message(items_by_source):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"🌍 *Dunyo yangiliklari* — {now}", "_(sarlavhalar avtomatik tarjima qilingan)_", ""]

    for source, items in items_by_source.items():
        lines.append(f"*{source}*")
        for item in items:
            title = item["title"].replace("[", "(").replace("]", ")")
            lines.append(f"• [{title}]({item['link']})")
        lines.append("")

    return "\n".join(lines).strip()


def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]

    for chunk in chunks:
        resp = requests.post(url, data={
            "chat_id": CHANNEL_ID,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        })
        if resp.status_code != 200:
            print(f"[XATO] Telegram javobi: {resp.status_code} {resp.text}")
            resp.raise_for_status()


def main():
    posted_ids = load_posted_ids()
    items_by_source = fetch_new_items(posted_ids)

    if not items_by_source:
        print("Yangi xabar topilmadi — hech narsa jo'natilmadi.")
        return

    message = build_message(items_by_source)
    send_to_telegram(message)
    print("Xabar muvaffaqiyatli jo'natildi.")

    for items in items_by_source.values():
        for item in items:
            posted_ids.add(item["link"])
    save_posted_ids(posted_ids)


if __name__ == "__main__":
    main()
