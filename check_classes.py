#!/usr/bin/env python3
"""Check ProServe Manila intermediate group classes and alert on Telegram when slots open."""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

FEED_URL = "https://proservemanila.com/api/classes?venue=sta_ana"
BOOKING_URL = "https://proservemanila.com/booking/classes"
TIER = "intermediate"
STATE_FILE = Path(__file__).with_name("state.json")


def fetch_classes():
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "Mozilla/5.0 (proserve-watcher)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if not payload.get("success") or not isinstance(payload.get("data"), list):
        raise RuntimeError(f"Unexpected response: {str(payload)[:200]}")
    return [c for c in payload["data"] if c.get("tier") == TIER]


def bookable_slots(c):
    if c.get("status") != "open" or (c.get("secondsUntilRelease") or 0) > 0:
        return 0
    return c.get("availableSlots") or 0


def label(c):
    return f"{c['dateLabel']} · {c['timeLabel']} — {bookable_slots(c)}/{c['totalSlots']} slots"


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[dry run: Telegram not configured]\n" + text)
        return
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with urllib.request.urlopen(url, data=data, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Telegram error {resp.status}")


def main():
    classes = fetch_classes()
    previous = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    current = {c["id"]: bookable_slots(c) for c in classes}

    # Alert when a class goes from 0 (or unseen) to having open slots.
    newly_open = [c for c in classes if current[c["id"]] > 0 and previous.get(c["id"], 0) == 0]
    all_open = [c for c in classes if current[c["id"]] > 0]
    print(f"{len(classes)} intermediate classes, {len(all_open)} with open slots, {len(newly_open)} newly open")

    if newly_open or "--test" in sys.argv:
        lines = ["🎾 ProServe intermediate slots open!" if newly_open else "🎾 ProServe watcher test message"]
        if newly_open:
            lines += ["", "New:"] + [f"• {label(c)}" for c in newly_open]
        others = [c for c in all_open if c not in newly_open]
        if others:
            lines += ["", "Still open:"] + [f"• {label(c)}" for c in others]
        if not all_open:
            lines += ["", f"All {len(classes)} intermediate classes are currently full."]
        lines += ["", f"Book: {BOOKING_URL}"]
        send_telegram("\n".join(lines))

    if current != previous:
        STATE_FILE.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
