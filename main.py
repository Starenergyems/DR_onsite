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


class DaySelectCBLRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    assumed_adjust_avg_kw: Optional[float] = Field(
        None, description="若在事件前計算 CBL，可假設事件日 22:00-24:00 平均需量，未提供則以 0 計算 AF"
    )
    records: List[MeterRecord]
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
    assumed_adjust_avg_kw: Optional[float] = Field(
        None, description="事件前可提供假設之 22:00-24:00 平均需量；未提供則 AF 預設 0"
    )
    records: List[MeterRecord]
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


# 新增：日選實際抑低容量 (減載) 計算之回應模型
class DaySelectReductionRequest(BaseModel):
    """計算日選時段型事件的實際抑低容量請求模型。"""

    customer_id: str
    event_start: datetime
    event_end: datetime
    assumed_adjust_avg_kw: Optional[float] = Field(
        None, description="事件前可提供假設之 22:00-24:00 平均需量；未提供則 AF 預設 0"
    )
    records: List[MeterRecord]
    contract_capacity_kw: Optional[float] = None
    committed_capacity_kw: Optional[float] = None


class DaySelectReductionResponse(BaseModel):
    """回傳日選時段型事件的基準用電與實際抑低容量及執行率。"""

    customer_id: str
    event_start: datetime
    event_end: datetime
    cbl_kw: float
    actual_avg_kw: float
    actual_reduction_kw: float
    committed_capacity_kw: Optional[float] = None
    execution_rate: Optional[float] = None
    reduction_ratio: Optional[float] = None
    baseline_source_days: List[date]
    method: str
    detail: Dict[str, float]


# -------------------------
# 保證反應型 (Guaranteed Response) 模型
# -------------------------

class GuaranteedEventRequest(BaseModel):
    """計算保證反應型單次事件基準與實際抑低容量的請求。

    參數說明：
    - customer_id: 用戶 ID。
    - event_start/event_end: 抑低用電事件開始與結束時間。
    - notification_minutes_before: 通知時間提前分鐘數，可為 30、60 或 120。
    - contract_capacity_kw: 抑低契約容量 (瓩)。
    - basic_fee_rate: 每瓩每月之基本電費扣減費率，若未提供則依通知時間套用預設值。
    - flow_fee_rate: 每度之流動電費扣減費率，若未提供則依規範預設值。
    """

    customer_id: str
    event_start: datetime
    event_end: datetime
    records: List[MeterRecord]
    notification_minutes_before: int = Field(..., description="通知提前分鐘數，值須為 30、60 或 120")
    contract_capacity_kw: float = Field(..., gt=0, description="抑低契約容量 (瓩)")
    committed_capacity_kw: Optional[float] = Field(
        None, description="約定抑低契約容量，未提供則以 contract_capacity_kw 為準"
    )
    basic_fee_rate: Optional[float] = Field(
        None, description="基本電費扣減費率 (每瓩每月)，若未提供則依通知時間預設"
    )
    flow_fee_rate: Optional[float] = Field(
        None, description="流動電費扣減費率 (每度)，若未提供則依規範預設"
    )


class GuaranteedEventDetail(BaseModel):
    event_start: datetime
    event_end: datetime
    baseline_kw: float
    actual_avg_kw: float
    actual_reduction_kw: float
    execution_rate: float
    event_duration_hours: float
    flow_reduction_amount: float
    extra_charge_amount: float
    detail: Dict[str, float]


class GuaranteedEventResponse(BaseModel):
    """保證反應型單次事件計算結果。"""
    customer_id: str
    event_start: datetime
    event_end: datetime
    baseline_kw: float
    actual_reduction_kw: float
    execution_rate: float
    event_duration_hours: float
    flow_reduction_amount: float
    extra_charge_amount: float
    detail: Dict[str, float]


class GuaranteedRewardEvent(BaseModel):
    """月度計算中單次事件的基本資訊。"""

    customer_id: str
    event_start: datetime
    event_end: datetime
    committed_capacity_kw: Optional[float] = Field(
        None, description="事件約定抑低契約容量，未提供則套用月度或契約容量"
    )


class GuaranteedRewardRequest(BaseModel):
    """計算保證反應型月度電費扣減之請求。"""

    customer_id: str
    notification_minutes_before: int = Field(..., description="通知提前分鐘數，30、60 或 120")
    contract_capacity_kw: float = Field(..., gt=0, description="抑低契約容量 (瓩)")
    events: List[GuaranteedRewardEvent] = Field(
        ..., description="本月所有抑低事件清單，每項事件需包含開始與結束時間"
    )
    committed_capacity_kw: Optional[float] = Field(
        None, description="月度約定抑低契約容量，事件未提供時沿用，否則退回契約容量"
    )
    records: List[MeterRecord]
    basic_fee_rate: Optional[float] = None
    flow_fee_rate: Optional[float] = None


class GuaranteedRewardResponse(BaseModel):
    """保證反應型月度電費扣減計算結果。"""

    customer_id: str
    contract_capacity_kw: float
    average_execution_rate: float
    reduction_ratio: float
    basic_fee_rate: float
    flow_fee_rate: float
    basic_reduction_amount: float
    flow_reduction_total_amount: float
    extra_charge_total_amount: float
    net_reward_amount: float
    event_details: List[GuaranteedEventDetail]

# 新增：保證反應型僅計算基準用電之請求及回應模型
class GuaranteedCBLRequest(BaseModel):
    """計算保證反應型單次事件基準用電的請求。"""

    customer_id: str
    event_start: datetime
    records: List[MeterRecord]
    notification_minutes_before: int = Field(..., description="通知提前分鐘數，30、60 或 120")
    contract_capacity_kw: float = Field(..., gt=0, description="抑低契約容量 (瓩)")


class GuaranteedCBLResponse(BaseModel):
    """保證反應型基準用電計算結果。"""

    customer_id: str
    event_start: datetime
    notification_minutes_before: int
    baseline_kw: float
    detail: Dict[str, float]


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
    # Treat weekends as off-peak for baseline exclusion
    return d.weekday() >= 5  # Saturday, Sunday


def is_in_day_select_season(d: date) -> bool:
    return (d.month > 5 or (d.month == 5 and d.day >= 1)) and (
        d.month < 10 or (d.month == 10 and d.day <= 31)
    )


def get_customer_records(records: List[MeterRecord], customer_id: str) -> List[MeterRecord]:
    """Filter and sort records for a specific customer."""
    customer_records = [r for r in records if r.customer_id == customer_id]
    return sorted(customer_records, key=lambda r: r.timestamp)


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


def _ensure_no_duplicate_timestamps(records: List[MeterRecord], customer_id: str):
    seen = set()
    for r in records:
        ts = to_taipei(r.timestamp)
        # use timezone-normalized timestamp as uniqueness key
        if ts in seen:
            raise HTTPException(400, f"{customer_id} 有重複時間戳 {ts.isoformat()}")
        seen.add(ts)


def _ensure_15min_alignment(records: List[MeterRecord], customer_id: str):
    for r in records:
        ts = to_taipei(r.timestamp)
        if ts.minute % 15 != 0 or ts.second != 0 or ts.microsecond != 0:
            raise HTTPException(400, f"{customer_id} 的時間戳未對齊 15 分鐘：{ts.isoformat()}")


def validate_customer_records(records: List[MeterRecord], customer_id: str) -> List[MeterRecord]:
    """Validate and return sorted customer records."""
    customer_records = get_customer_records(records, customer_id)
    if not customer_records:
        raise HTTPException(404, "沒有此客戶的電表資料")
    _ensure_no_duplicate_timestamps(customer_records, customer_id)
    _ensure_15min_alignment(customer_records, customer_id)
    return customer_records


def _build_window_range(base_date: date, start_t: time, end_t: time) -> (datetime, datetime):
    start_dt = to_taipei(datetime.combine(base_date, start_t))
    end_date = base_date + timedelta(days=1) if end_t <= start_t else base_date
    end_dt = to_taipei(datetime.combine(end_date, end_t))
    return start_dt, end_dt


def _ensure_full_window(records: List[MeterRecord], start_dt: datetime, end_dt: datetime, label: str):
    """Ensure every 15-minute slot within [start_dt, end_dt) is present."""
    if start_dt >= end_dt:
        raise HTTPException(400, f"{label} 時間範圍無效")
    if (start_dt.minute % 15 != 0) or (start_dt.second != 0) or (start_dt.microsecond != 0):
        raise HTTPException(400, f"{label} 起始時間未對齊 15 分鐘：{start_dt.isoformat()}")
    if (end_dt.minute % 15 != 0) or (end_dt.second != 0) or (end_dt.microsecond != 0):
        raise HTTPException(400, f"{label} 結束時間未對齊 15 分鐘：{end_dt.isoformat()}")
    step = timedelta(minutes=15)
    duration = end_dt - start_dt
    if duration.total_seconds() % step.total_seconds() != 0:
        raise HTTPException(400, f"{label} 長度非 15 分鐘整數倍")
    expected_slots = int(duration.total_seconds() // step.total_seconds())
    ts_set = {to_taipei(r.timestamp) for r in records if start_dt <= to_taipei(r.timestamp) < end_dt}
    missing: List[datetime] = []
    cursor = start_dt
    for _ in range(expected_slots):
        if cursor not in ts_set:
            missing.append(cursor)
        cursor += step
    if missing:
        preview = ", ".join(dt.isoformat() for dt in missing[:5])
        raise HTTPException(400, f"{label} 缺少 {len(missing)} 筆 15 分鐘區間，例: {preview}")


def _reject_records_outside_windows(records: List[MeterRecord], windows: List[tuple], customer_id: str):
    """Reject records whose timestamps are not within any allowed window."""
    for r in records:
        ts = to_taipei(r.timestamp)
        if not any(start <= ts < end for start, end in windows):
            raise HTTPException(400, f"{customer_id} 包含超出需求時間窗的資料：{ts.isoformat()}")


def _filter_records_in_windows(records: List[MeterRecord], windows: List[tuple]) -> List[MeterRecord]:
    """Return records whose timestamps fall within any given window."""
    kept = []
    for r in records:
        ts = to_taipei(r.timestamp)
        if any(start <= ts < end for start, end in windows):
            kept.append(r)
    return kept


def filter_records_between(records: List[MeterRecord], start_dt: datetime, end_dt: datetime) -> List[MeterRecord]:
    """取得介於 start_dt（含）與 end_dt（不含）之記錄。時間可能跨日。"""
    start_ts = to_taipei(start_dt)
    end_ts = to_taipei(end_dt)
    matched: List[MeterRecord] = []
    for r in records:
        ts = to_taipei(r.timestamp)
        if start_ts <= ts < end_ts:
            matched.append(r)
    return matched


# -------------------------
# 核心：日選 CBL 計算
# -------------------------
def compute_day_select_cbl(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    records: List[MeterRecord],
    assumed_today_adjust_avg_kw: Optional[float] = None,
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

    customer_records = validate_customer_records(records, customer_id)

    # 1. 搜尋前 20 個合格日
    baseline_days: List[date] = []
    current_day = event_date - timedelta(days=1)
    searched = 0
    search_limit = 90
    event_start_t = event_start.time()
    event_end_t = event_end.time()
    allowed_windows = []

    while len(baseline_days) < min_baseline_days and searched < search_limit:
        if (
            not is_weekend(current_day)
            and not is_off_peak_day(current_day)
            and is_in_day_select_season(current_day)
        ):
            r = filter_records_by_time_window(customer_records, current_day, event_start_t, event_end_t)
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
        recs = filter_records_by_time_window(customer_records, d, event_start_t, event_end_t)
        avg = average_kw(recs)
        if avg is not None:
            event_window_avgs.append(avg)

    baseline_event_avg_kw = sum(event_window_avgs) / len(event_window_avgs)

    # 3. 負載調整因子（下午 10 時至 12 時 = 22:00–24:00）
    adjust_start = time(22, 0)
    adjust_end = time(0, 0)

    hist_adjust = []
    # 確認基準日視窗完整
    for d in baseline_days:
        base_event_start_dt, base_event_end_dt = _build_window_range(d, event_start_t, event_end_t)
        _ensure_full_window(customer_records, base_event_start_dt, base_event_end_dt, f"基準日 {d} 事件時段")
        allowed_windows.append((base_event_start_dt, base_event_end_dt))

        base_adjust_start_dt, base_adjust_end_dt = _build_window_range(d, adjust_start, adjust_end)
        _ensure_full_window(customer_records, base_adjust_start_dt, base_adjust_end_dt, f"基準日 {d} 22:00-24:00")
        allowed_windows.append((base_adjust_start_dt, base_adjust_end_dt))

    for d in baseline_days:
        recs = filter_records_cross_day(customer_records, d, adjust_start, adjust_end)
        avg = average_kw(recs)
        if avg is not None:
            hist_adjust.append(avg)

    hist_adjust_avg_kw = sum(hist_adjust) / len(hist_adjust) if hist_adjust else 0.0

    event_adjust_start_dt, event_adjust_end_dt = _build_window_range(event_date, adjust_start, adjust_end)
    assumed_adjust_used = False
    if assumed_today_adjust_avg_kw is not None:
        today_adjust_avg = assumed_today_adjust_avg_kw
        assumed_adjust_used = True
    else:
        _ensure_full_window(customer_records, event_adjust_start_dt, event_adjust_end_dt, f"事件日 {event_date} 22:00-24:00")
        today_recs = filter_records_cross_day(customer_records, event_date, adjust_start, adjust_end)
        today_adjust_avg = average_kw(today_recs) or 0.0
    allowed_windows.append((event_adjust_start_dt, event_adjust_end_dt))

    # 事件時段窗口（允許資料存在、CBL 不要求完整，供後續實際抑低/回饋使用）
    event_window_start_dt, event_window_end_dt = _build_window_range(event_date, event_start_t, event_end_t)
    allowed_windows.append((event_window_start_dt, event_window_end_dt))

    _reject_records_outside_windows(customer_records, allowed_windows, customer_id)

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
            "assumed_today_adjust_avg_kw": assumed_today_adjust_avg_kw if assumed_adjust_used else None,
        },
    )


# -------------------------
# 新增：日選回饋金計算
# -------------------------
def compute_day_select_reward(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    records: List[MeterRecord],
    committed_capacity_kw: float,
    contract_capacity_kw: Optional[float] = None,
    assumed_today_adjust_avg_kw: Optional[float] = None,
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
        records=records,
        assumed_today_adjust_avg_kw=assumed_today_adjust_avg_kw,
        contract_capacity_kw=contract_capacity_kw,
        min_baseline_days=min_baseline_days,
    )
    cbl_kw = cbl_resp.cbl_kw

    # 事件時區轉換
    event_start = to_taipei(event_start)
    event_end = to_taipei(event_end)
    event_date = event_start.date()
    # 取得此用戶所有紀錄
    customer_records = validate_customer_records(records, customer_id)
    event_window_start_dt, event_window_end_dt = _build_window_range(event_date, event_start.time(), event_end.time())
    _ensure_full_window(customer_records, event_window_start_dt, event_window_end_dt, f"事件日 {event_date} 事件時段")
    # 取得實際平均需量
    if event_end.date() != event_date:
        actual_recs = filter_records_cross_day(customer_records, event_date, event_start.time(), event_end.time())
    else:
        actual_recs = filter_records_by_time_window(customer_records, event_date, event_start.time(), event_end.time())
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
# 日選實際抑低容量計算
# -------------------------

def compute_day_select_reduction(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    records: List[MeterRecord],
    assumed_today_adjust_avg_kw: Optional[float] = None,
    contract_capacity_kw: Optional[float] = None,
    committed_capacity_kw: Optional[float] = None,
    min_baseline_days: int = 20,
):
    """
    計算日選時段型事件的基準用電 (CBL) 與實際抑低容量。

    - 首先調用 compute_day_select_cbl 取得基準用電。
    - 接著計算事件時段的實際平均需量 actual_avg_kw。
    - 實際抑低容量 actual_reduction_kw = max(cbl_kw - actual_avg_kw, 0)。

    此函式用於執行調度指令後獨立評估實際抑低容量，不包含回饋金計算。
    """
    # 計算基準用電
    cbl_resp = compute_day_select_cbl(
        customer_id=customer_id,
        event_start=event_start,
        event_end=event_end,
        records=records,
        assumed_today_adjust_avg_kw=assumed_today_adjust_avg_kw,
        contract_capacity_kw=contract_capacity_kw,
        min_baseline_days=min_baseline_days,
    )
    cbl_kw = cbl_resp.cbl_kw
    # 轉換時區
    event_start = to_taipei(event_start)
    event_end = to_taipei(event_end)
    event_date = event_start.date()
    # 取得實際事件平均需量
    customer_records = validate_customer_records(records, customer_id)
    event_window_start_dt, event_window_end_dt = _build_window_range(event_date, event_start.time(), event_end.time())
    _ensure_full_window(customer_records, event_window_start_dt, event_window_end_dt, f"事件日 {event_date} 事件時段")
    if event_end.date() != event_date:
        actual_recs = filter_records_cross_day(customer_records, event_date, event_start.time(), event_end.time())
    else:
        actual_recs = filter_records_by_time_window(customer_records, event_date, event_start.time(), event_end.time())
    actual_avg_kw = average_kw(actual_recs) or 0.0
    actual_reduction_kw = max(cbl_kw - actual_avg_kw, 0.0)
    # 計算執行率與扣減比率（若提供 committed_capacity_kw）
    exec_rate = None
    reduction_ratio = None
    if committed_capacity_kw is not None and committed_capacity_kw > 0:
        x_ratio = actual_reduction_kw / committed_capacity_kw
        x_ratio_rounded = round(x_ratio, 1)
        # 上限 1.2
        if x_ratio_rounded > 1.2:
            x_ratio_rounded = 1.2
        exec_rate = x_ratio_rounded
        # 扣減比率
        if exec_rate < 0.6:
            reduction_ratio = 0.0
        elif exec_rate < 0.8:
            reduction_ratio = 0.8
        elif exec_rate < 0.95:
            reduction_ratio = 1.0
        else:
            reduction_ratio = 1.2
    # 詳細資訊
    detail = cbl_resp.detail.copy()
    detail.update({
        "actual_avg_kw": actual_avg_kw,
        "actual_reduction_kw": actual_reduction_kw,
    })
    if exec_rate is not None:
        detail.update({
            "execution_rate": exec_rate,
            "reduction_ratio": reduction_ratio,
        })
    return DaySelectReductionResponse(
        customer_id=customer_id,
        event_start=event_start,
        event_end=event_end,
        cbl_kw=cbl_kw,
        actual_avg_kw=actual_avg_kw,
        actual_reduction_kw=actual_reduction_kw,
        committed_capacity_kw=committed_capacity_kw,
        execution_rate=exec_rate,
        reduction_ratio=reduction_ratio,
        baseline_source_days=cbl_resp.baseline_source_days,
        method="day-select-reduction-v1",
        detail=detail,
    )


# -------------------------
# 保證反應型計算
# -------------------------

def compute_guaranteed_event(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    notification_minutes_before: int,
    contract_capacity_kw: float,
    records: List[MeterRecord],
    committed_capacity_kw: Optional[float] = None,
    basic_fee_rate: Optional[float] = None,
    flow_fee_rate: Optional[float] = None,
):
    """
    計算保證反應型單次事件之基準用電、實際抑低容量與執行率，並估算流動電費扣減與加計電費。

    1. 基準用電容量：通知時間前 2 小時之 15 分鐘平均需量平均值。
    2. 實際抑低容量：基準用電容量減去抑低用電時段平均需量，若為負值則為 0。
    3. 執行率：實際抑低容量 / (約定抑低契約容量或抑低契約容量)，四捨五入至小數 1 位，最高 100%。
    4. 流動電費扣減：當次執行率≥70% 時，按 實際抑低容量×執行抑低時數×流動電費扣減費率 計算；否則為 0。
    5. 加計電費：當次執行率 <60% 時，計算 (1 - 執行率) × (約定抑低契約容量或抑低契約容量) ×執行時數×流動電費扣減費率×2；否則為 0。

    參數：
    - notification_minutes_before：通知前幾分鐘。可為 30、60 或 120。
    - basic_fee_rate：基本電費扣減費率 (每瓩每月)。若為 None，依通知提前時間套用 93、84、78。
    - flow_fee_rate：流動電費扣減費率 (每度)。若為 None，預設為 12。
    """

    event_start = to_taipei(event_start)
    event_end = to_taipei(event_end)
    if event_end <= event_start:
        raise HTTPException(400, "event_end 必須晚於 event_start")

    # 檢核通知時間選項
    if notification_minutes_before not in (30, 60, 120):
        raise HTTPException(400, "notification_minutes_before 必須為 30、60 或 120")

    # 預設基本費率
    if basic_fee_rate is None:
        if notification_minutes_before == 30:
            basic_fee_rate = 93.0
        elif notification_minutes_before == 60:
            basic_fee_rate = 84.0
        else:  # 120
            basic_fee_rate = 78.0
    # 預設流動費率
    if flow_fee_rate is None:
        flow_fee_rate = 12.0

    # 計算通知時間
    notification_time = event_start - timedelta(minutes=notification_minutes_before)
    baseline_start = notification_time - timedelta(hours=2)
    baseline_end = notification_time

    customer_records = validate_customer_records(records, customer_id)
    # 確認必要視窗完整
    _ensure_full_window(customer_records, baseline_start, baseline_end, "通知前 2 小時")
    _ensure_full_window(customer_records, event_start, event_end, "事件時段")

    allowed_windows = [(baseline_start, baseline_end), (event_start, event_end)]
    _reject_records_outside_windows(customer_records, allowed_windows, customer_id)

    # 取得基準用電期間紀錄
    baseline_records = filter_records_between(customer_records, baseline_start, baseline_end)
    baseline_kw = average_kw(baseline_records) or 0.0

    # 取得事件期間實際平均需量
    actual_records = filter_records_between(customer_records, event_start, event_end)
    actual_avg_kw = average_kw(actual_records) or 0.0

    # 實際抑低容量
    actual_reduction_kw = max(baseline_kw - actual_avg_kw, 0.0)

    # 執行抑低時數 (小時)
    event_duration_hours = (event_end - event_start).total_seconds() / 3600.0

    # 執行率 (%): capped at 100%
    capacity_denom = committed_capacity_kw if committed_capacity_kw is not None else contract_capacity_kw
    if capacity_denom <= 0:
        raise HTTPException(400, "committed_capacity_kw (或 contract_capacity_kw) 必須大於 0")

    exec_rate = actual_reduction_kw / capacity_denom
    # 四捨五入小數一位並截 100%
    exec_rate_rounded = min(round(exec_rate, 1), 1.0)

    # 流動電費扣減
    flow_reduction_amount = 0.0
    if exec_rate_rounded >= 0.7:
        flow_reduction_amount = actual_reduction_kw * event_duration_hours * flow_fee_rate

    # 加計電費
    extra_charge_amount = 0.0
    if exec_rate_rounded < 0.6:
        # (1 - 執行率) ×契約容量×時數×費率×2
        extra_charge_amount = (1.0 - exec_rate_rounded) * capacity_denom * event_duration_hours * flow_fee_rate * 2.0

    detail = {
        "baseline_start": baseline_start.isoformat(),
        "baseline_end": baseline_end.isoformat(),
        "baseline_kw": baseline_kw,
        "actual_avg_kw": actual_avg_kw,
        "actual_reduction_kw": actual_reduction_kw,
        "execution_rate": exec_rate_rounded,
        "capacity_denom_kw": capacity_denom,
        "committed_capacity_kw": committed_capacity_kw,
        "event_duration_hours": event_duration_hours,
        "flow_fee_rate": flow_fee_rate,
        "flow_reduction_amount": flow_reduction_amount,
        "extra_charge_amount": extra_charge_amount,
    }

    return GuaranteedEventResponse(
        customer_id=customer_id,
        event_start=event_start,
        event_end=event_end,
        baseline_kw=baseline_kw,
        actual_reduction_kw=actual_reduction_kw,
        execution_rate=exec_rate_rounded,
        event_duration_hours=event_duration_hours,
        flow_reduction_amount=flow_reduction_amount,
        extra_charge_amount=extra_charge_amount,
        detail=detail,
    )


def compute_guaranteed_reward(
    customer_id: str,
    notification_minutes_before: int,
    contract_capacity_kw: float,
    events: List[GuaranteedRewardEvent],
    records: List[MeterRecord],
    committed_capacity_kw: Optional[float] = None,
    basic_fee_rate: Optional[float] = None,
    flow_fee_rate: Optional[float] = None,
):
    """
    計算保證反應型月度電費扣減總額。

    每月電費扣減 = 基本電費扣減 + 流動電費扣減總和 - 加計電費總和。

    - 基本電費扣減 = 抑低契約容量 × 基本電費扣減費率 × 扣減比率
      扣減比率依平均執行率決定：
        平均執行率 < 70% → 0
        70% ≤ x < 80% → 0.6
        80% ≤ x < 95% → 0.8
        x ≥ 95% → 1.0
    - 流動電費扣減：對於每次事件，若執行率 ≥ 70%，則實際抑低容量 × 時數 × 流動電費扣減費率；否則 0。
    - 加計電費：對於每次事件，若執行率 < 60%，則 (1 - 執行率) × 契約容量 × 時數 × 流動電費扣減費率 × 2；否則 0。
    - 若當月無執行事件，基本電費扣減 = 抑低契約容量 × 基本電費扣減費率，無流動扣減與加計電費。

    回傳包括各事件細節、平均執行率、扣減比率、各項金額與總計。
    """

    # 檢核通知時間
    if notification_minutes_before not in (30, 60, 120):
        raise HTTPException(400, "notification_minutes_before 必須為 30、60 或 120")

    # 預設基本費率
    if basic_fee_rate is None:
        if notification_minutes_before == 30:
            basic_fee_rate = 93.0
        elif notification_minutes_before == 60:
            basic_fee_rate = 84.0
        else:
            basic_fee_rate = 78.0
    # 預設流動費率
    if flow_fee_rate is None:
        flow_fee_rate = 12.0

    customer_records = validate_customer_records(records, customer_id)

    # 預先彙整所有事件需求視窗以拒絕多餘資料
    allowed_windows: List[tuple] = []
    for ev in events:
        ev_start = to_taipei(ev.event_start)
        ev_end = to_taipei(ev.event_end)
        baseline_end = ev_start - timedelta(minutes=notification_minutes_before)
        baseline_start = baseline_end - timedelta(hours=2)
        allowed_windows.append((baseline_start, baseline_end))
        allowed_windows.append((ev_start, ev_end))

    _reject_records_outside_windows(customer_records, allowed_windows, customer_id)

    event_details: List[GuaranteedEventDetail] = []
    execution_rates: List[float] = []
    flow_total = 0.0
    extra_total = 0.0

    for ev in events:
        event_committed = ev.committed_capacity_kw
        if event_committed is None:
            event_committed = committed_capacity_kw
        if event_committed is None:
            event_committed = contract_capacity_kw
        ev_start = to_taipei(ev.event_start)
        ev_end = to_taipei(ev.event_end)
        baseline_end = ev_start - timedelta(minutes=notification_minutes_before)
        baseline_start = baseline_end - timedelta(hours=2)
        event_windows = [(baseline_start, baseline_end), (ev_start, ev_end)]
        event_records = _filter_records_in_windows(customer_records, event_windows)
        # 每個事件使用相同的通知時間、費率、契約容量
        result = compute_guaranteed_event(
            customer_id=ev.customer_id,
            event_start=ev_start,
            event_end=ev_end,
            notification_minutes_before=notification_minutes_before,
            contract_capacity_kw=contract_capacity_kw,
            committed_capacity_kw=event_committed,
            records=event_records,
            basic_fee_rate=basic_fee_rate,
            flow_fee_rate=flow_fee_rate,
        )
        execution_rates.append(result.execution_rate)
        flow_total += result.flow_reduction_amount
        extra_total += result.extra_charge_amount
        event_details.append(
            GuaranteedEventDetail(
                event_start=result.event_start,
                event_end=result.event_end,
                baseline_kw=result.baseline_kw,
                actual_avg_kw=result.detail.get("actual_avg_kw", 0.0),
                actual_reduction_kw=result.actual_reduction_kw,
                execution_rate=result.execution_rate,
                event_duration_hours=result.event_duration_hours,
                flow_reduction_amount=result.flow_reduction_amount,
                extra_charge_amount=result.extra_charge_amount,
                detail=result.detail,
            )
        )

    # 若無執行事件
    if not event_details:
        average_execution = 0.0
        reduction_ratio = 1.0  # 按規範，未通知執行抑低用電之月份：基本電費扣減=契約容量×基本費率
        basic_reduction = contract_capacity_kw * basic_fee_rate
        net_reward = basic_reduction
        return GuaranteedRewardResponse(
            customer_id=customer_id,
            contract_capacity_kw=contract_capacity_kw,
            average_execution_rate=average_execution,
            reduction_ratio=reduction_ratio,
            basic_fee_rate=basic_fee_rate,
            flow_fee_rate=flow_fee_rate,
            basic_reduction_amount=basic_reduction,
            flow_reduction_total_amount=0.0,
            extra_charge_total_amount=0.0,
            net_reward_amount=net_reward,
            event_details=event_details,
        )

    # 計算平均執行率
    average_execution = sum(execution_rates) / len(execution_rates)

    # 扣減比率
    if average_execution < 0.7:
        reduction_ratio = 0.0
    elif average_execution < 0.8:
        reduction_ratio = 0.6
    elif average_execution < 0.95:
        reduction_ratio = 0.8
    else:
        reduction_ratio = 1.0

    # 基本電費扣減
    basic_reduction = contract_capacity_kw * basic_fee_rate * reduction_ratio

    # 總獎勵 = 基本電費扣減 + 流動電費扣減總和 - 加計電費總和
    net_reward = basic_reduction + flow_total - extra_total

    return GuaranteedRewardResponse(
        customer_id=customer_id,
        contract_capacity_kw=contract_capacity_kw,
        average_execution_rate=average_execution,
        reduction_ratio=reduction_ratio,
        basic_fee_rate=basic_fee_rate,
        flow_fee_rate=flow_fee_rate,
        basic_reduction_amount=basic_reduction,
        flow_reduction_total_amount=flow_total,
        extra_charge_total_amount=extra_total,
        net_reward_amount=net_reward,
        event_details=event_details,
    )


# -------------------------
# 保證反應型：基準用電計算
# -------------------------

def compute_guaranteed_cbl(
    customer_id: str,
    event_start: datetime,
    records: List[MeterRecord],
    notification_minutes_before: int,
    contract_capacity_kw: float,
    flow_fee_rate: Optional[float] = None,
):
    """
    計算保證反應型事件的基準用電 (基準需量)。

    基準需量為通知時間前 2 小時之 15 分鐘平均需量平均值【574061540680747†L208-L238】。
    僅計算基準用電，不包含實際抑低容量與費率計算，可於指令調度前使用。
    """
    # 檢核通知時間
    if notification_minutes_before not in (30, 60, 120):
        raise HTTPException(400, "notification_minutes_before 必須為 30、60 或 120")
    # 預設流動費率 (不直接用於基準計算，但可從 compute_guaranteed_event 引用)
    if flow_fee_rate is None:
        flow_fee_rate = 12.0
    # 確認 contract_capacity_kw 有效
    if contract_capacity_kw <= 0:
        raise HTTPException(400, "contract_capacity_kw 必須大於 0")
    event_start = to_taipei(event_start)
    # 計算通知時間及基準區間
    notification_time = event_start - timedelta(minutes=notification_minutes_before)
    baseline_start = notification_time - timedelta(hours=2)
    baseline_end = notification_time
    customer_records = validate_customer_records(records, customer_id)
    _ensure_full_window(customer_records, baseline_start, baseline_end, "通知前 2 小時")
    _reject_records_outside_windows(customer_records, [(baseline_start, baseline_end)], customer_id)
    baseline_records = filter_records_between(customer_records, baseline_start, baseline_end)
    baseline_kw = average_kw(baseline_records) or 0.0
    detail = {
        "baseline_start": baseline_start.isoformat(),
        "baseline_end": baseline_end.isoformat(),
        "baseline_kw": baseline_kw,
    }
    return GuaranteedCBLResponse(
        customer_id=customer_id,
        event_start=event_start,
        notification_minutes_before=notification_minutes_before,
        baseline_kw=baseline_kw,
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
        "\n- /dr/guaranteed/event：計算保證反應型單次事件基準與實際抑低容量。"
        "\n- /dr/guaranteed/reward：計算保證反應型月度電費扣減總額。"
    ),
)

@app.post("/dr/day-select/cbl", response_model=DaySelectCBLResponse)
def api_day_select_cbl(req: DaySelectCBLRequest):
    return compute_day_select_cbl(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        assumed_today_adjust_avg_kw=req.assumed_adjust_avg_kw,
        contract_capacity_kw=req.contract_capacity_kw,
    )


@app.post("/dr/day-select/reward", response_model=DaySelectRewardResponse)
def api_day_select_reward(req: DaySelectRewardRequest):
    """計算日選時段型的流動電費扣減 (回饋金)。"""
    return compute_day_select_reward(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        assumed_today_adjust_avg_kw=req.assumed_adjust_avg_kw,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
    )


# 新增：計算日選實際抑低容量
@app.post("/dr/day-select/reduction", response_model=DaySelectReductionResponse)
def api_day_select_reduction(req: DaySelectReductionRequest):
    """計算日選時段型事件的基準用電與實際抑低容量及執行率。"""
    return compute_day_select_reduction(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        assumed_today_adjust_avg_kw=req.assumed_adjust_avg_kw,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
    )





# 新增：保證反應型基準用電計算
@app.post("/dr/guaranteed/cbl", response_model=GuaranteedCBLResponse)
def api_guaranteed_cbl(req: GuaranteedCBLRequest):
    """計算保證反應型事件的基準用電 (僅計算通知前 2 小時平均)。"""
    return compute_guaranteed_cbl(
        customer_id=req.customer_id,
        event_start=req.event_start,
        records=req.records,
        notification_minutes_before=req.notification_minutes_before,
        contract_capacity_kw=req.contract_capacity_kw,
    )


# 新增：保證反應型實際抑低容量計算 (別名)
@app.post("/dr/guaranteed/reduction", response_model=GuaranteedEventResponse)
def api_guaranteed_reduction(req: GuaranteedEventRequest):
    """計算保證反應型事件的基準用電與實際抑低容量。"""
    return compute_guaranteed_event(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        notification_minutes_before=req.notification_minutes_before,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
        records=req.records,
        basic_fee_rate=req.basic_fee_rate,
        flow_fee_rate=req.flow_fee_rate,
    )


@app.post("/dr/guaranteed/reward", response_model=GuaranteedRewardResponse)
def api_guaranteed_reward(req: GuaranteedRewardRequest):
    """計算保證反應型月度電費扣減總額。"""
    return compute_guaranteed_reward(
        customer_id=req.customer_id,
        notification_minutes_before=req.notification_minutes_before,
        contract_capacity_kw=req.contract_capacity_kw,
        events=req.events,
        records=req.records,
        committed_capacity_kw=req.committed_capacity_kw,
        basic_fee_rate=req.basic_fee_rate,
        flow_fee_rate=req.flow_fee_rate,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", port=18000, host="0.0.0.0", reload=True)
