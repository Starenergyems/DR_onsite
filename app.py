"""Demand response API layer for on-site control.

This module exposes a FastAPI app with a dayDR endpoint that validates
incoming demand response calls against business rules and calculates the
CBL (Criteria Base Load) when applicable.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

import redis
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field, validator

app = FastAPI(title="Demand Response API", version="1.0.0")


@dataclass
class RedisConfig:
    url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    def client(self) -> redis.Redis:
        return redis.Redis.from_url(self.url, decode_responses=True)


def get_redis_client(config: RedisConfig = RedisConfig()) -> redis.Redis:
    return config.client()


class TimeSpan(BaseModel):
    start: datetime
    end: datetime

    @validator("end")
    def validate_order(cls, end: datetime, values: dict) -> datetime:
        start: datetime | None = values.get("start")
        if start and end <= start:
            raise ValueError("end must be after start")
        return end


class DayDRRequest(BaseModel):
    measure: str = Field(..., description="DR measure name (e.g., dayDR)")
    capacityDR: float = Field(..., description="Requested DR capacity in kW")
    timespanDR: TimeSpan
    timezone: str | None = Field(
        default=None,
        description="IANA timezone name used to evaluate local rules. Defaults to TZ env or UTC.",
    )

    @validator("capacityDR")
    def validate_capacity(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("capacityDR must be positive")
        return value


class DayDRResponse(BaseModel):
    accepted: bool
    reason: str | None = None
    cbl: float | None = None


ALLOWED_WINDOWS: set[tuple[time, time]] = {
    (time(18, 0), time(20, 0)),
    (time(16, 0), time(20, 0)),
    (time(16, 0), time(22, 0)),
}


@app.post("/dayDR", response_model=DayDRResponse)
def handle_day_dr(request: DayDRRequest, redis_client: redis.Redis = Depends(get_redis_client)):
    if request.measure != "dayDR":
        return DayDRResponse(accepted=False, reason="Unsupported measure")

    target_tz = ZoneInfo(_resolve_timezone(request.timezone))
    local_start = request.timespanDR.start.astimezone(target_tz)
    local_end = request.timespanDR.end.astimezone(target_tz)

    contract_value = _read_contract_value(redis_client)
    if contract_value is None or contract_value <= 100:
        return DayDRResponse(accepted=False, reason="Contract value below threshold")

    if not _is_valid_window(local_start, local_end):
        return DayDRResponse(accepted=False, reason="Timespan not in allowed DR windows")

    if not _is_in_active_season(local_start):
        return DayDRResponse(accepted=False, reason="Request outside active DR season")

    if request.capacityDR <= 20:
        return DayDRResponse(accepted=False, reason="capacityDR must exceed 20 kW")

    load_profile = _read_load_profile(redis_client)
    cbl_value = _calculate_cbl(load_profile, local_start, local_end, target_tz)
    return DayDRResponse(accepted=True, cbl=cbl_value)


def _resolve_timezone(request_tz: str | None) -> str:
    if request_tz:
        return request_tz
    return os.getenv("TZ", "UTC")


def _read_contract_value(redis_client: redis.Redis) -> float | None:
    raw = redis_client.get("setting_json")
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    value = payload.get("contract_value")
    return float(value) if value is not None else None


def _is_valid_window(start: datetime, end: datetime) -> bool:
    weekday = start.weekday()
    if weekday > 4:  # Saturday=5, Sunday=6
        return False

    window = (start.timetz().replace(tzinfo=None), end.timetz().replace(tzinfo=None))
    for allowed_start, allowed_end in ALLOWED_WINDOWS:
        if window[0] == allowed_start and window[1] == allowed_end:
            return True
    return False


def _is_in_active_season(start: datetime) -> bool:
    month = start.month
    day = start.day
    if month < 5 or month > 10:
        return False
    if month == 5 and day < 1:
        return False
    if month == 10 and day > 31:
        return False
    return True


def _read_load_profile(redis_client: redis.Redis) -> list[dict]:
    raw = redis_client.get("load_profile:15m")
    if not raw:
        raise HTTPException(status_code=503, detail="Load profile unavailable")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Invalid load profile format") from exc
    if not isinstance(data, list):
        raise HTTPException(status_code=500, detail="Load profile must be a list")
    return data


def _calculate_cbl(load_profile: Sequence[dict], start: datetime, end: datetime, tz: ZoneInfo) -> float:
    window_start = start.timetz().replace(tzinfo=None)
    window_end = end.timetz().replace(tzinfo=None)
    call_date = start.date()
    earliest_date = call_date - timedelta(days=20)

    daily_minima: list[float] = []
    for entry in _iter_entries(load_profile):
        local_dt = entry.timestamp.astimezone(tz)
        if local_dt.date() >= call_date or local_dt.date() < earliest_date:
            continue
        if local_dt.time() < window_start or local_dt.time() > window_end:
            continue
        daily_minima.append((local_dt.date(), entry.kw))

    minima_by_date: dict = {}
    for day, kw in daily_minima:
        minima_by_date[day] = min(minima_by_date.get(day, kw), kw)

    if not minima_by_date:
        raise HTTPException(status_code=422, detail="Insufficient load profile for CBL calculation")

    return sum(minima_by_date.values()) / len(minima_by_date)


@dataclass
class LoadEntry:
    timestamp: datetime
    kw: float


def _iter_entries(entries: Sequence[dict]) -> Iterable[LoadEntry]:
    for entry in entries:
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            kw = float(entry["kw"])
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=500, detail="Malformed load profile entry") from exc
        yield LoadEntry(timestamp=ts, kw=kw)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
