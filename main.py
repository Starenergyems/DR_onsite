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


# 新增：日選回饋金計算的請求模型
class DaySelectRewardRequest(BaseModel):
    """用於計算日選時段型回饋金的請求體。

    參數說明：
    - customer_id: 用戶識別碼。
    - event_start/event_end: DR 事件開始與結束時間（含時區）。
    - contract_capacity_kw: 經常契約容量 CBL2，用於計算基準用電上限。
    - committed_capacity_kw: 約定抑低契約容量，用於計算執行率與回饋金。
    """
    customer_id: str
    event_start: datetime
    event_end: datetime
    contract_capacity_kw: Optional[float] = None
    committed_capacity_kw: float


# 新增：日選回饋金計算的回應模型
class DaySelectRewardResponse(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    committed_capacity_kw: float
    cbl_kw: float
    actual_avg_kw: float
    actual_reduction_kw: float
    execution_rate: float
    reduction_ratio: float
    tariff_rate: float
    event_duration_hours: float
    reward_ntd: float
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
# 新增：日選回饋金計算
# -------------------------
def compute_day_select_reward(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    contract_capacity_kw: Optional[float],
    committed_capacity_kw: float,
    min_baseline_days: int = 20,
):
    """
    計算日選時段型的回饋金（流動電費扣減）。

    步驟：
    1. 先計算基準用電 (CBL)，使用 compute_day_select_cbl。
    2. 取得事件日同時段實際平均需量，計算實際抑低容量 = max(CBL - 當日平均, 0)。
    3. 計算執行率 = (實際抑低容量 / 約定抑低契約容量)，四捨五入至小數第 1 位，最高為 120%。
    4. 依執行率決定扣減比率：<60% → 0；60%≤x<80% → 0.8；80%≤x<95% → 1.0；x≥95% → 1.2。
    5. 依事件時段長度選取每度扣減費率：2 小時→2.47、4 小時→1.84、6 小時→1.69（元/度）。
    6. 回饋金 = 約定抑低契約容量 × 執行率 × 執行時數 × 每度扣減費率 × 扣減比率。

    備註：此函式假設事件時段為 2、4、6 小時之一；若非此範圍將拋出例外。
    """
    # 計算基準用電（CBL）
    cbl_resp = compute_day_select_cbl(
        customer_id=customer_id,
        event_start=event_start,
        event_end=event_end,
        contract_capacity_kw=contract_capacity_kw,
        min_baseline_days=min_baseline_days,
    )
    cbl_kw = cbl_resp.cbl_kw

    # 事件時區轉換
    event_start = to_taipei(event_start)
    event_end = to_taipei(event_end)
    event_date = event_start.date()
    # 取得此用戶所有紀錄
    records = get_customer_records(customer_id)
    # 取得實際平均需量
    if event_end.date() != event_date:
        actual_recs = filter_records_cross_day(records, event_date, event_start.time(), event_end.time())
    else:
        actual_recs = filter_records_by_time_window(records, event_date, event_start.time(), event_end.time())
    actual_avg_kw = average_kw(actual_recs) or 0.0

    # 實際抑低容量
    actual_reduction_kw = max(cbl_kw - actual_avg_kw, 0.0)

    # 檢查約定抑低契約容量
    if committed_capacity_kw <= 0:
        raise HTTPException(400, "committed_capacity_kw 必須為正值")

    # 執行率 (ratio)
    x_ratio = actual_reduction_kw / committed_capacity_kw
    # 四捨五入到小數一位
    x_ratio_rounded = round(x_ratio, 1)
    # 上限 1.2
    if x_ratio_rounded > 1.2:
        x_ratio_rounded = 1.2

    # 扣減比率
    if x_ratio_rounded < 0.6:
        reduction_ratio = 0.0
    elif x_ratio_rounded < 0.8:
        reduction_ratio = 0.8
    elif x_ratio_rounded < 0.95:
        reduction_ratio = 1.0
    else:
        reduction_ratio = 1.2

    # 計算事件時數 (小時)
    event_duration_hours = (event_end - event_start).total_seconds() / 3600.0
    # 選擇每度扣減費率
    if abs(event_duration_hours - 2) < 0.1:
        tariff_rate = 2.47
    elif abs(event_duration_hours - 4) < 0.1:
        tariff_rate = 1.84
    elif abs(event_duration_hours - 6) < 0.1:
        tariff_rate = 1.69
    else:
        raise HTTPException(
            400,
            f"不支援的執行時數 {event_duration_hours} 小時 (僅支援 2、4、6 小時)",
        )

    # 計算回饋金 (元)
    reward_ntd = (
        committed_capacity_kw
        * x_ratio_rounded
        * event_duration_hours
        * tariff_rate
        * reduction_ratio
    )

    # 細節資訊複製基準用電資訊並附加回饋計算相關資料
    detail = cbl_resp.detail.copy()
    detail.update(
        {
            "actual_avg_kw": actual_avg_kw,
            "actual_reduction_kw": actual_reduction_kw,
            "execution_rate_ratio": x_ratio_rounded,
            "reduction_ratio": reduction_ratio,
            "tariff_rate": tariff_rate,
            "event_duration_hours": event_duration_hours,
            "reward_ntd": reward_ntd,
        }
    )

    return DaySelectRewardResponse(
        customer_id=customer_id,
        event_start=event_start,
        event_end=event_end,
        committed_capacity_kw=committed_capacity_kw,
        cbl_kw=cbl_kw,
        actual_avg_kw=actual_avg_kw,
        actual_reduction_kw=actual_reduction_kw,
        execution_rate=x_ratio_rounded,
        reduction_ratio=reduction_ratio,
        tariff_rate=tariff_rate,
        event_duration_hours=event_duration_hours,
        reward_ntd=reward_ntd,
        baseline_source_days=cbl_resp.baseline_source_days,
        method="day-select-reward-v1",
        detail=detail,
    )


# -------------------------
# FastAPI
# -------------------------
app = FastAPI(
    title="Taipower DR API Server",
    version="1.1.0",
    description=(
        "日選 DR API：提供基準用電 (CBL) 計算與回饋金試算。\n"
        "- /dr/day-select/cbl：計算基準用電 (CBL)。\n"
        "- /dr/day-select/reward：計算當日流動電費扣減 (回饋金)。"
    ),
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


@app.post("/dr/day-select/reward", response_model=DaySelectRewardResponse)
def api_day_select_reward(req: DaySelectRewardRequest):
    """計算日選時段型的流動電費扣減 (回饋金)。"""
    return compute_day_select_reward(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", port=18000, host="0.0.0.0", reload=True)