"""Seed Redis with demo data for the dayDR endpoint.

This script populates:
- setting_json: contract_value 150
- load_profile:15m: 20 days of 15-minute samples with a daily trough window

Usage:
    python scripts/seed_demo.py --redis redis://localhost:6379/0 --timezone Asia/Taipei
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, time
from random import randint
from zoneinfo import ZoneInfo

import redis


DEFAULT_TZ = "UTC"
SLOT_MINUTES = 15


def _build_load_profile(tz: ZoneInfo) -> list[dict]:
    entries: list[dict] = []
    now = datetime.now(tz)
    # generate past 20 days excluding today
    for day_offset in range(1, 21):
        day = now.date() - timedelta(days=day_offset)
        base_kw = 100 + randint(-5, 5)
        trough_kw = 70 + randint(-3, 3)
        trough_start = time(18, 0)
        trough_end = time(20, 0)
        current = datetime.combine(day, time(0, 0), tz)
        end_of_day = current + timedelta(days=1)
        while current < end_of_day:
            kw = trough_kw if trough_start <= current.time() <= trough_end else base_kw
            entries.append({"timestamp": current.isoformat(), "kw": kw})
            current += timedelta(minutes=SLOT_MINUTES)
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Redis with demo DR data")
    parser.add_argument("--redis", default="redis://localhost:6379/0", help="Redis URL")
    parser.add_argument("--timezone", default=DEFAULT_TZ, help="IANA timezone")
    args = parser.parse_args()

    tz = ZoneInfo(args.timezone)
    client = redis.Redis.from_url(args.redis, decode_responses=True)

    setting_payload = {"contract_value": 150}
    client.set("setting_json", json.dumps(setting_payload))

    profile = _build_load_profile(tz)
    client.set("load_profile:15m", json.dumps(profile))

    print("Seeded setting_json and load_profile:15m", f"for timezone {args.timezone}")


if __name__ == "__main__":
    main()
