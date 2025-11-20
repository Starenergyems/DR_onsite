from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app import app, get_redis_client


class FakeRedis:
    def __init__(self, data):
        self.data = data

    def get(self, key):
        return self.data.get(key)


def build_load_profile(call_date):
    tz = ZoneInfo("UTC")
    entries = []
    for days_back in range(1, 21):
        day = call_date - timedelta(days=days_back)
        # Two samples within the window; the minimum will be kw_base
        kw_base = 10 + days_back
        entries.append({
            "timestamp": datetime.combine(day, datetime.min.time(), tz).replace(hour=16).isoformat(),
            "kw": kw_base,
        })
        entries.append({
            "timestamp": datetime.combine(day, datetime.min.time(), tz).replace(hour=18).isoformat(),
            "kw": kw_base + 5,
        })
    return entries


def override_redis(data):
    fake = FakeRedis(data)
    app.dependency_overrides[get_redis_client] = lambda: fake
    return fake


def test_day_dr_accepts_and_returns_cbl():
    call_start = datetime(2024, 6, 5, 16, 0, tzinfo=ZoneInfo("UTC"))
    call_end = datetime(2024, 6, 5, 20, 0, tzinfo=ZoneInfo("UTC"))

    load_profile = build_load_profile(call_start.date())
    override_redis({
        "setting_json": "{\"contract_value\": 200}",
        "load_profile:15m": json_dumps(load_profile),
    })

    client = TestClient(app)
    response = client.post(
        "/dayDR",
        json={
            "measure": "dayDR",
            "capacityDR": 25,
            "timespanDR": {
                "start": call_start.isoformat(),
                "end": call_end.isoformat(),
            },
            "timezone": "UTC",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] is True
    assert round(payload["cbl"], 2) == 20.5


def test_day_dr_rejects_when_contract_low():
    call_start = datetime(2024, 6, 5, 16, 0, tzinfo=ZoneInfo("UTC"))
    call_end = datetime(2024, 6, 5, 20, 0, tzinfo=ZoneInfo("UTC"))

    override_redis({"setting_json": "{\"contract_value\": 50}"})

    client = TestClient(app)
    response = client.post(
        "/dayDR",
        json={
            "measure": "dayDR",
            "capacityDR": 25,
            "timespanDR": {
                "start": call_start.isoformat(),
                "end": call_end.isoformat(),
            },
            "timezone": "UTC",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "accepted": False,
        "reason": "Contract value below threshold",
        "cbl": None,
    }


def test_day_dr_rejects_unsupported_measure():
    call_start = datetime(2024, 6, 5, 16, 0, tzinfo=ZoneInfo("UTC"))
    call_end = datetime(2024, 6, 5, 20, 0, tzinfo=ZoneInfo("UTC"))

    override_redis({"setting_json": "{\"contract_value\": 200}"})

    client = TestClient(app)
    response = client.post(
        "/dayDR",
        json={
            "measure": "guaranteeDR",
            "capacityDR": 25,
            "timespanDR": {
                "start": call_start.isoformat(),
                "end": call_end.isoformat(),
            },
            "timezone": "UTC",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "accepted": False,
        "reason": "Unsupported measure",
        "cbl": None,
    }


def json_dumps(obj):
    # Local helper avoids importing json at module import time to keep overrides clear.
    import json

    return json.dumps(obj)
