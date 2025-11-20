from datetime import datetime, timedelta, time, date
from typing import List, Dict, Optional

import pytz
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# -------------------------
# 設定
# -------------------------
TZ = pytz.timezone("Asia/Taipei")

# 離峰日可由台電時間電價日曆表配置；此處留空方便測試
OFF_PEAK_SPECIAL_DAYS: List[date] = []


# -------------------------
# Pydantic Models
# -------------------------
class MeterRecord(BaseModel):
    customer_id: str
    timestamp: datetime
    kw: float = Field(..., ge=0)


class BulkMeterIngestRequest(BaseModel):
    records: List[MeterRecord]


class DaySelectCBLRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    # 經常契約容量(瓩)。若提供，CBL 將取 min(CBL1+AF, CBL2)。
    contract_capacity_kw: Optional[float] = None


class DaySelectCBLResponse(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    cbl_kw: float  # 最終基準用電容量 (CBL)
    baseline_source_days: List[date]
    method: str
    detail: Dict[str, float]


# -------------------------
# In-memory 儲存
# -------------------------
METER_STORE: Dict[str, List[MeterRecord]] = {}


# -------------------------
# 工具函式
# -------------------------
def to_taipei(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return TZ.localize(dt)
    return dt.astimezone(TZ)


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_off_peak_day(d: date) -> bool:
    if d in OFF_PEAK_SPECIAL_DAYS:
        return True
    return d.weekday() == 6  # Sunday


def is_in_day_select_season(d: date) -> bool:
    return (d.month > 5 or (d.month == 5 and d.day >= 1)) and (
        d.month < 10 or (d.month == 10 and d.day <= 31)
    )


def get_customer_records(customer_id: str) -> List[MeterRecord]:
    if customer_id not in METER_STORE:
        return []
    return sorted(METER_STORE[customer_id], key=lambda r: r.timestamp)


def filter_records_by_time_window(records, target_date, start_t, end_t):
    matched = []
    for r in records:
        ts = to_taipei(r.timestamp)
        if ts.date() != target_date:
            continue
        if start_t <= ts.time() < end_t:
            matched.append(r)
    return matched


def filter_records_cross_day(records, target_date, start_t, end_t):
    matched = []
    for r in records:
        ts = to_taipei(r.timestamp)
        if ts.date() == target_date and ts.time() >= start_t:
            matched.append(r)
        if ts.date() == (target_date + timedelta(days=1)) and ts.time() < end_t:
            matched.append(r)
    return matched


def average_kw(records: List[MeterRecord]) -> Optional[float]:
    if not records:
        return None
    return sum(r.kw for r in records) / len(records)


# -------------------------
# 核心：日選 CBL 計算
# -------------------------
def compute_day_select_cbl(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    contract_capacity_kw: Optional[float] = None,
    min_baseline_days: int = 20,
):
    event_start = to_taipei(event_start)
    event_end = to_taipei(event_end)

    if event_end <= event_start:
        raise HTTPException(400, "event_end 必須晚於 event_start")

    event_date = event_start.date()

    if not is_in_day_select_season(event_date):
        raise HTTPException(
            400,
            "事件日期不在日選期間（5月1日至10月31日）內",
        )

    records = get_customer_records(customer_id)
    if not records:
        raise HTTPException(404, "沒有此客戶的電表資料")

    # 1. 搜尋前 20 個合格日
    baseline_days: List[date] = []
    current_day = event_date - timedelta(days=1)
    searched = 0
    search_limit = 90
    event_start_t = event_start.time()
    event_end_t = event_end.time()

    while len(baseline_days) < min_baseline_days and searched < search_limit:
        if (
            not is_weekend(current_day)
            and not is_off_peak_day(current_day)
            and is_in_day_select_season(current_day)
        ):
            r = filter_records_by_time_window(records, current_day, event_start_t, event_end_t)
            if r:
                baseline_days.append(current_day)
        current_day -= timedelta(days=1)
        searched += 1

    if len(baseline_days) < min_baseline_days:
        raise HTTPException(
            400,
            f"資料不足以形成前 {min_baseline_days} 個合格日，只找到 {len(baseline_days)} 日",
        )

    # 2. 計算前 20 日事件時段平均需量
    event_window_avgs = []
    for d in baseline_days:
        recs = filter_records_by_time_window(records, d, event_start_t, event_end_t)
        avg = average_kw(recs)
        if avg is not None:
            event_window_avgs.append(avg)

    baseline_event_avg_kw = sum(event_window_avgs) / len(event_window_avgs)

    # 3. 負載調整因子（下午 10 時至 12 時 = 22:00–24:00）
    adjust_start = time(22, 0)
    adjust_end = time(0, 0)

    hist_adjust = []
    for d in baseline_days:
        recs = filter_records_cross_day(records, d, adjust_start, adjust_end)
        avg = average_kw(recs)
        if avg is not None:
            hist_adjust.append(avg)

    hist_adjust_avg_kw = sum(hist_adjust) / len(hist_adjust) if hist_adjust else 0.0

    today_recs = filter_records_cross_day(records, event_date, adjust_start, adjust_end)
    today_adjust_avg = average_kw(today_recs) or 0.0

    load_adjust_factor = max(today_adjust_avg - hist_adjust_avg_kw, 0.0)

    # CBL1: baseline_event_avg_kw, AF: load_adjust_factor
    cbl1_kw = baseline_event_avg_kw
    af_kw = load_adjust_factor
    cbl1_plus_af_kw = cbl1_kw + af_kw
    # CBL2: contract capacity if provided, else very large number (no cap)
    cbl2_kw = contract_capacity_kw if contract_capacity_kw is not None else cbl1_plus_af_kw
    # Final CBL: min(CBL1+AF, CBL2)
    final_cbl = cbl1_plus_af_kw if cbl1_plus_af_kw < cbl2_kw else cbl2_kw

    return DaySelectCBLResponse(
        customer_id=customer_id,
        event_start=event_start,
        event_end=event_end,
        cbl_kw=final_cbl,
        baseline_source_days=sorted(baseline_days),
        method="day-select-cbl-v1",
        detail={
            "cbl1_kw": cbl1_kw,
            "af_kw": af_kw,
            "cbl1_plus_af_kw": cbl1_plus_af_kw,
            "cbl2_kw": cbl2_kw,
            "cbl_kw": final_cbl,
            "hist_adjust_avg_kw": hist_adjust_avg_kw,
            "today_adjust_avg_kw": today_adjust_avg,
        },
    )


# -------------------------
# FastAPI
# -------------------------
app = FastAPI(
    title="Taipower DR API Server",
    version="1.0.0",
    description="日選 DR CBL 計算（含下午10時至12時負載調整因子）",
)


@app.post("/meter-data/batch")
def ingest_meter_data(req: BulkMeterIngestRequest):
    count = 0
    for r in req.records:
        cid = r.customer_id
        if cid not in METER_STORE:
            METER_STORE[cid] = []
        METER_STORE[cid].append(r)
        count += 1
    return {"status": "ok", "inserted": count}


@app.post("/dr/day-select/cbl", response_model=DaySelectCBLResponse)
def api_day_select_cbl(req: DaySelectCBLRequest):
    return compute_day_select_cbl(
        req.customer_id,
        req.event_start,
        req.event_end,
        req.contract_capacity_kw,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", port=18000, host="0.0.0.0", reload=True)