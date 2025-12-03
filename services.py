from datetime import datetime, timedelta, time, date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple

import pytz
from fastapi import HTTPException

from schemas import (
    DRPeriod,
    DaySelectCBLResponse,
    DaySelectReductionResponse,
    DaySelectRewardResponse,
    DaySelectMonthlySettlementResponse,
    DaySelectMonthlyEvent,
    GuaranteedCBLResponse,
    GuaranteedEventDetail,
    GuaranteedEventResponse,
    GuaranteedRewardEvent,
    GuaranteedRewardResponse,
    MeterRecord,
    RequiredDay,
    DaySelectRequiredPreResponse,
    DaySelectRequiredPostResponse,
    GuaranteedRequiredPreResponse,
    GuaranteedRequiredPostResponse,
    SpinReserveCBLResponse,
    SpinReserveRequiredResponse,
    RequiredWindow,
)

# -------------------------
# 設定
# -------------------------
TZ = pytz.timezone("Asia/Taipei")
OFF_PEAK_SPECIAL_DAYS: List[date] = []


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
    return d.weekday() >= 5


def parse_dr_periods(dr_periods: List[DRPeriod]) -> List[Tuple[date, date]]:
    parsed: List[Tuple[date, date]] = []
    for p in dr_periods:
        def _parse_one(s: str, is_start: bool) -> date:
            parts = s.split("-")
            if len(parts) == 2:
                y, m = map(int, parts)
                if is_start:
                    return date(y, m, 1)
                if m == 12:
                    return date(y, 12, 31)
                from calendar import monthrange
                last_day = monthrange(y, m)[1]
                return date(y, m, last_day)
            if len(parts) == 3:
                y, m, d = map(int, parts)
                return date(y, m, d)
            raise HTTPException(400, f"dr_periods 日期格式錯誤：{s}")

        start_d = _parse_one(p.start, True)
        end_d = _parse_one(p.end, False)
        if end_d < start_d:
            raise HTTPException(400, f"dr_periods 起訖順序錯誤：{p.start} - {p.end}")
        parsed.append((start_d, end_d))
    return parsed


def is_in_dr_period(target: date, dr_periods: List[Tuple[date, date]]) -> bool:
    return any(s <= target <= e for s, e in dr_periods)


def previous_november_first(event_date: date) -> date:
    if event_date.month > 11 or (event_date.month == 11 and event_date.day > 1):
        return date(event_date.year, 11, 1)
    return date(event_date.year - 1, 11, 1)


def get_customer_records(records: List[MeterRecord], customer_id: str) -> List[MeterRecord]:
    customer_records = [r for r in records if r.customer_id == customer_id]
    return sorted(customer_records, key=lambda r: r.timestamp)


def filter_records_by_time_window(records, target_date, start_t, end_t):
    matched = []
    for r in records:
        ts = to_taipei(r.timestamp)
        if ts.date() != target_date:
            continue
        if start_t < ts.time() <= end_t:
            matched.append(r)
    return matched


def filter_records_cross_day(records, target_date, start_t, end_t):
    matched = []
    for r in records:
        ts = to_taipei(r.timestamp)
        if ts.date() == target_date and ts.time() > start_t:
            matched.append(r)
        if ts.date() == (target_date + timedelta(days=1)) and ts.time() <= end_t:
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
        if ts in seen:
            raise HTTPException(400, f"{customer_id} 有重複時間戳 {ts.isoformat()}")
        seen.add(ts)


def _ensure_15min_alignment(records: List[MeterRecord], customer_id: str):
    for r in records:
        ts = to_taipei(r.timestamp)
        if ts.minute % 15 != 0 or ts.second != 0 or ts.microsecond != 0:
            raise HTTPException(400, f"{customer_id} 的時間戳未對齊 15 分鐘：{ts.isoformat()}")


def _ensure_step_alignment(records: List[MeterRecord], customer_id: str, step_minutes: int):
    if step_minutes <= 0:
        raise HTTPException(400, "step_minutes 必須為正值")
    for r in records:
        ts = to_taipei(r.timestamp)
        if ts.second != 0 or ts.microsecond != 0:
            raise HTTPException(400, f"{customer_id} 的時間戳未對齊 {step_minutes} 分鐘：{ts.isoformat()}")
        if ts.minute % step_minutes != 0:
            raise HTTPException(400, f"{customer_id} 的時間戳未對齊 {step_minutes} 分鐘：{ts.isoformat()}")


def validate_customer_records(records: List[MeterRecord], customer_id: str) -> List[MeterRecord]:
    customer_records = get_customer_records(records, customer_id)
    if not customer_records:
        raise HTTPException(404, "沒有此客戶的電表資料")
    _ensure_no_duplicate_timestamps(customer_records, customer_id)
    _ensure_15min_alignment(customer_records, customer_id)
    return customer_records


def validate_customer_records_step(records: List[MeterRecord], customer_id: str, step_minutes: int) -> List[MeterRecord]:
    customer_records = get_customer_records(records, customer_id)
    if not customer_records:
        raise HTTPException(404, "沒有此客戶的電表資料")
    _ensure_no_duplicate_timestamps(customer_records, customer_id)
    _ensure_step_alignment(customer_records, customer_id, step_minutes)
    return customer_records


def _build_window_range(base_date: date, start_t: time, end_t: time) -> (datetime, datetime):
    start_dt = to_taipei(datetime.combine(base_date, start_t))
    end_date = base_date + timedelta(days=1) if end_t <= start_t else base_date
    end_dt = to_taipei(datetime.combine(end_date, end_t))
    return start_dt, end_dt


def _normalize_day_select_window(event_start: datetime, event_end: datetime, batch_time_tariff: bool) -> (datetime, datetime):
    start = to_taipei(event_start)
    end = to_taipei(event_end)
    return start, end


def _validate_day_select_event_window(event_start: datetime, event_end: datetime, batch_time_tariff: bool):
    event_date = event_start.date()
    if is_weekend(event_date) or is_off_peak_day(event_date):
        raise HTTPException(400, "事件日期須為工作日且非離峰日")

    if batch_time_tariff:
        if event_start.time() != time(15, 30) or event_end.time() != time(21, 30):
            raise HTTPException(400, "批次生產時間電價事件時段固定為 15:30-21:30")
        return

    allowed_slots = [
        (time(18, 0), time(20, 0)),
        (time(16, 0), time(20, 0)),
        (time(16, 0), time(22, 0)),
    ]
    if not any(event_start.time() == s and event_end.time() == e for s, e in allowed_slots):
        raise HTTPException(400, "事件時段僅支援 18:00-20:00、16:00-20:00、16:00-22:00")


def _validate_guaranteed_event_window(event_start: datetime, event_end: datetime):
    event_date = event_start.date()
    if is_weekend(event_date) or is_off_peak_day(event_date):
        raise HTTPException(400, "事件日期須為工作日且非離峰日")
    start_t = event_start.time()
    if not (time(13, 0) <= start_t <= time(22, 0)):
        raise HTTPException(400, "執行起始時間僅允許 13:00-22:00")
    if event_end <= event_start:
        raise HTTPException(400, "event_end 必須晚於 event_start")
    duration_hours = (event_end - event_start).total_seconds() / 3600.0
    if duration_hours not in (2.0, 3.0, 4.0):
        raise HTTPException(400, "保證型執行時數僅允許 2、3 或 4 小時")


def _validate_guaranteed_capacity(contract_capacity_kw: float, committed_capacity_kw: Optional[float] = None):
    if contract_capacity_kw < 1000:
        raise HTTPException(400, "經常契約容量須達 1,000 瓩以上，方可符合最低約定抑低容量要求")
    if committed_capacity_kw is None:
        raise HTTPException(400, "約定抑低契約容量必填")
    min_committed = max(1000.0, contract_capacity_kw * 0.15)
    if committed_capacity_kw < min_committed:
        raise HTTPException(400, f"約定抑低契約容量須達 1,000 瓩或經常契約容量的 15% 以上 (最低 {min_committed:.1f} 瓩)")
    if committed_capacity_kw > contract_capacity_kw:
        raise HTTPException(400, "約定抑低契約容量不可大於經常契約容量")


def _validate_day_select_capacity(contract_capacity_kw: float, committed_capacity_kw: Optional[float] = None):
    if contract_capacity_kw < 100:
        raise HTTPException(400, "日選型經常契約容量須達 100 瓩以上")
    if committed_capacity_kw is not None and committed_capacity_kw < 20:
        raise HTTPException(400, "日選型最低約定抑低契約容量須達 20 瓩")


def _ensure_full_window(records: List[MeterRecord], start_dt: datetime, end_dt: datetime, label: str):
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
    ts_set = {to_taipei(r.timestamp) for r in records if start_dt < to_taipei(r.timestamp) <= end_dt}
    missing: List[datetime] = []
    cursor = start_dt + step
    for _ in range(expected_slots):
        if cursor not in ts_set:
            missing.append(cursor)
        cursor += step
    if missing:
        preview = ", ".join(dt.isoformat() for dt in missing[:5])
        raise HTTPException(400, f"{label} 缺少 {len(missing)} 筆 15 分鐘區間，例: {preview}")


def _ensure_full_window_step(
    records: List[MeterRecord],
    start_dt: datetime,
    end_dt: datetime,
    label: str,
    step_minutes: int,
):
    if start_dt >= end_dt:
        raise HTTPException(400, f"{label} 時間範圍無效")
    if (start_dt.second != 0) or (start_dt.microsecond != 0):
        raise HTTPException(400, f"{label} 起始時間秒數需為 0：{start_dt.isoformat()}")
    if (end_dt.second != 0) or (end_dt.microsecond != 0):
        raise HTTPException(400, f"{label} 結束時間秒數需為 0：{end_dt.isoformat()}")
    step = timedelta(minutes=step_minutes)
    duration = end_dt - start_dt
    if duration.total_seconds() % step.total_seconds() != 0:
        raise HTTPException(400, f"{label} 長度需為 {step_minutes} 分鐘的整數倍")
    expected_slots = int(duration.total_seconds() // step.total_seconds())
    ts_set = {to_taipei(r.timestamp) for r in records if start_dt < to_taipei(r.timestamp) <= end_dt}
    missing: List[datetime] = []
    cursor = start_dt + step
    for _ in range(expected_slots):
        if cursor not in ts_set:
            missing.append(cursor)
        cursor += step
    if missing:
        preview = ", ".join(dt.isoformat() for dt in missing[:5])
        raise HTTPException(400, f"{label} 缺少 {len(missing)} 筆 {step_minutes} 分鐘區間，例: {preview}")


def _reject_records_outside_windows(records: List[MeterRecord], windows: List[tuple], customer_id: str):
    for r in records:
        ts = to_taipei(r.timestamp)
        if not any(start < ts <= end for start, end in windows):
            raise HTTPException(400, f"{customer_id} 包含超出需求時間窗的資料：{ts.isoformat()}")


def _filter_records_in_windows(records: List[MeterRecord], windows: List[tuple]) -> List[MeterRecord]:
    kept = []
    for r in records:
        ts = to_taipei(r.timestamp)
        if any(start < ts <= end for start, end in windows):
            kept.append(r)
    return kept


def filter_records_between(records: List[MeterRecord], start_dt: datetime, end_dt: datetime) -> List[MeterRecord]:
    start_ts = to_taipei(start_dt)
    end_ts = to_taipei(end_dt)
    matched: List[MeterRecord] = []
    for r in records:
        ts = to_taipei(r.timestamp)
        if start_ts < ts <= end_ts:
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
    contract_capacity_kw: float,
    committed_capacity_kw: float,
    dr_periods: Optional[List[DRPeriod]] = None,
    batch_time_tariff: bool = False,
    assumed_af_kw: Optional[float] = None,
    min_baseline_days: int = 20,
):
    event_start, event_end = _normalize_day_select_window(event_start, event_end, batch_time_tariff)

    if event_end <= event_start:
        raise HTTPException(400, "event_end 必須晚於 event_start")

    _validate_day_select_capacity(contract_capacity_kw, committed_capacity_kw)

    event_date = event_start.date()

    if not dr_periods:
        raise HTTPException(400, "dr_periods 必填")
    dr_period_ranges = parse_dr_periods(dr_periods)
    if not is_in_dr_period(event_date, dr_period_ranges):
        raise HTTPException(400, "事件日期未落在合約約定的抑低期間")

    _validate_day_select_event_window(event_start, event_end, batch_time_tariff)

    customer_records = validate_customer_records(records, customer_id)

    baseline_days: List[date] = []
    current_day = event_date - timedelta(days=1)
    boundary = previous_november_first(event_date)
    event_start_t = event_start.time()
    event_end_t = event_end.time()
    allowed_windows = []

    while len(baseline_days) < min_baseline_days and current_day >= boundary:
        if (
            not is_weekend(current_day)
            and not is_off_peak_day(current_day)
            and not is_in_dr_period(current_day, dr_period_ranges)
        ):
            r = filter_records_by_time_window(customer_records, current_day, event_start_t, event_end_t)
            if r:
                baseline_days.append(current_day)
        current_day -= timedelta(days=1)

    if len(baseline_days) < min_baseline_days:
        raise HTTPException(
            400,
            f"資料不足以形成前 {min_baseline_days} 個合格日（已回溯至上一個 11/1），只找到 {len(baseline_days)} 日",
        )

    event_window_avgs = []
    for d in baseline_days:
        recs = filter_records_by_time_window(customer_records, d, event_start_t, event_end_t)
        avg = average_kw(recs)
        if avg is not None:
            event_window_avgs.append(avg)

    baseline_event_avg_kw = sum(event_window_avgs) / len(event_window_avgs)

    adjust_start = time(22, 0)
    adjust_end = time(0, 0)

    hist_adjust = []
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
    today_adjust_avg = 0.0
    if assumed_af_kw is not None:
        today_adjust_avg = assumed_af_kw
        assumed_adjust_used = True
    else:
        try:
            _ensure_full_window(customer_records, event_adjust_start_dt, event_adjust_end_dt, f"事件日 {event_date} 22:00-24:00")
            today_recs = filter_records_cross_day(customer_records, event_date, adjust_start, adjust_end)
            today_adjust_avg = average_kw(today_recs) or 0.0
        except HTTPException:
            # 事件日 22-24 缺資料時，依規範 AF 預設 0
            today_adjust_avg = 0.0
    allowed_windows.append((event_adjust_start_dt, event_adjust_end_dt))

    event_window_start_dt, event_window_end_dt = _build_window_range(event_date, event_start_t, event_end_t)
    allowed_windows.append((event_window_start_dt, event_window_end_dt))

    load_adjust_factor = max(today_adjust_avg - hist_adjust_avg_kw, 0.0)

    cbl1_kw = baseline_event_avg_kw
    af_kw = load_adjust_factor
    cbl1_plus_af_kw = cbl1_kw + af_kw
    cbl2_kw = contract_capacity_kw if contract_capacity_kw is not None else cbl1_plus_af_kw
    final_cbl = cbl1_plus_af_kw if cbl1_plus_af_kw < cbl2_kw else cbl2_kw

    detail = {
        "cbl1_kw": cbl1_kw,
        "af_kw": af_kw,
        "cbl1_plus_af_kw": cbl1_plus_af_kw,
        "cbl2_kw": cbl2_kw,
        "cbl_kw": final_cbl,
        "hist_adjust_avg_kw": hist_adjust_avg_kw,
        "today_adjust_avg_kw": today_adjust_avg,
    }
    if assumed_adjust_used:
        detail["assumed_af_kw"] = assumed_af_kw

    target_load_kw = final_cbl - committed_capacity_kw

    return DaySelectCBLResponse(
        customer_id=customer_id,
        event_start=event_start,
        event_end=event_end,
        cbl_kw=final_cbl,
        target_load_kw=target_load_kw,
        baseline_source_days=sorted(baseline_days),
        method="day-select-cbl-v1",
        detail=detail,
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
    contract_capacity_kw: float,
    batch_time_tariff: bool = False,
    assumed_af_kw: Optional[float] = None,
    dr_periods: Optional[List[DRPeriod]] = None,
    min_baseline_days: int = 20,
):
    _validate_day_select_capacity(contract_capacity_kw, committed_capacity_kw)

    cbl_resp = compute_day_select_cbl(
        customer_id=customer_id,
        event_start=event_start,
        event_end=event_end,
        records=records,
        batch_time_tariff=batch_time_tariff,
        assumed_af_kw=assumed_af_kw,
        contract_capacity_kw=contract_capacity_kw,
        committed_capacity_kw=committed_capacity_kw,
        dr_periods=dr_periods,
        min_baseline_days=min_baseline_days,
    )
    cbl_kw = cbl_resp.cbl_kw

    event_start = to_taipei(cbl_resp.event_start)
    event_end = to_taipei(cbl_resp.event_end)
    event_date = event_start.date()
    customer_records = validate_customer_records(records, customer_id)
    event_window_start_dt, event_window_end_dt = _build_window_range(event_date, event_start.time(), event_end.time())
    _ensure_full_window(customer_records, event_window_start_dt, event_window_end_dt, f"事件日 {event_date} 事件時段")
    if event_end.date() != event_date:
        actual_recs = filter_records_cross_day(customer_records, event_date, event_start.time(), event_end.time())
    else:
        actual_recs = filter_records_by_time_window(customer_records, event_date, event_start.time(), event_end.time())
    actual_avg_kw = average_kw(actual_recs) or 0.0

    actual_reduction_kw = max(cbl_kw - actual_avg_kw, 0.0)
    target_load_kw = cbl_kw - committed_capacity_kw

    if committed_capacity_kw <= 0:
        raise HTTPException(400, "committed_capacity_kw 必須為正值")

    x_ratio = actual_reduction_kw / committed_capacity_kw
    x_ratio_rounded = round(x_ratio, 1)
    if x_ratio_rounded > 1.2:
        x_ratio_rounded = 1.2

    if x_ratio_rounded < 0.6:
        reduction_ratio = 0.0
    elif x_ratio_rounded < 0.8:
        reduction_ratio = 0.8
    elif x_ratio_rounded < 0.95:
        reduction_ratio = 1.0
    else:
        reduction_ratio = 1.2

    event_duration_hours = (event_end - event_start).total_seconds() / 3600.0
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

    reward_ntd = (
        committed_capacity_kw
        * x_ratio_rounded
        * event_duration_hours
        * tariff_rate
        * reduction_ratio
    )

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
            "target_load_kw": target_load_kw,
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
        target_load_kw=target_load_kw,
        baseline_source_days=cbl_resp.baseline_source_days,
        method="day-select-reward-v1",
        detail=detail,
    )


# -------------------------
# 日選：月度結算（多事件加總）
# -------------------------
def compute_day_select_settlement_monthly(
    customer_id: str,
    contract_capacity_kw: float,
    committed_capacity_kw: float,
    dr_periods: List[DRPeriod],
    records: List[MeterRecord],
    events: List[DaySelectMonthlyEvent],
    min_baseline_days: int = 20,
) -> DaySelectMonthlySettlementResponse:
    if not events:
        raise HTTPException(400, "events 不可為空")
    total_reward = 0.0
    total_reduction_kwh = 0.0
    results: List[DaySelectRewardResponse] = []
    for ev in events:
        event_committed = ev.committed_capacity_kw if ev.committed_capacity_kw is not None else committed_capacity_kw
        res = compute_day_select_reward(
            customer_id=customer_id,
            event_start=ev.event_start,
            event_end=ev.event_end,
            records=records,
            batch_time_tariff=ev.batch_time_tariff,
            assumed_af_kw=ev.assumed_af_kw,
            contract_capacity_kw=contract_capacity_kw,
            committed_capacity_kw=event_committed,
            dr_periods=dr_periods,
            min_baseline_days=min_baseline_days,
        )
        results.append(res)
        total_reward += res.reward_ntd
        total_reduction_kwh += res.actual_reduction_kw * res.event_duration_hours
    return DaySelectMonthlySettlementResponse(
        customer_id=customer_id,
        contract_capacity_kw=contract_capacity_kw,
        committed_capacity_kw=committed_capacity_kw,
        total_reward_ntd=total_reward,
        total_actual_reduction_kwh=total_reduction_kwh,
        events=results,
        method="day-select-settlement-monthly-v1",
    )

# -------------------------
# 日選實際抑低容量計算（含回饋金）
# -------------------------
def compute_day_select_reduction(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    records: List[MeterRecord],
    contract_capacity_kw: float,
    committed_capacity_kw: float,
    batch_time_tariff: bool = False,
    assumed_af_kw: Optional[float] = None,
    dr_periods: Optional[List[DRPeriod]] = None,
    min_baseline_days: int = 20,
):
    # 直接重用單次回饋金計算，確保回傳包含 reward_ntd 等欄位
    return compute_day_select_reward(
        customer_id=customer_id,
        event_start=event_start,
        event_end=event_end,
        records=records,
        batch_time_tariff=batch_time_tariff,
        assumed_af_kw=assumed_af_kw,
        contract_capacity_kw=contract_capacity_kw,
        committed_capacity_kw=committed_capacity_kw,
        dr_periods=dr_periods,
        min_baseline_days=min_baseline_days,
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
    committed_capacity_kw: float,
    basic_fee_rate: Optional[float] = None,
    flow_fee_rate: Optional[float] = None,
    dr_periods: Optional[List[DRPeriod]] = None,
):
    event_start = to_taipei(event_start)
    event_end = to_taipei(event_end)
    if event_end <= event_start:
        raise HTTPException(400, "event_end 必須晚於 event_start")

    _validate_guaranteed_event_window(event_start, event_end)
    _validate_guaranteed_capacity(contract_capacity_kw, committed_capacity_kw)
    if not dr_periods:
        raise HTTPException(400, "dr_periods 必填")
    dr_period_ranges = parse_dr_periods(dr_periods)
    if not is_in_dr_period(event_start.date(), dr_period_ranges):
        raise HTTPException(400, "事件日期未落在合約約定的抑低期間")

    if notification_minutes_before not in (30, 60, 120):
        raise HTTPException(400, "notification_minutes_before 必須為 30、60 或 120")

    if basic_fee_rate is None:
        if notification_minutes_before == 30:
            basic_fee_rate = 93.0
        elif notification_minutes_before == 60:
            basic_fee_rate = 84.0
        else:
            basic_fee_rate = 78.0
    if flow_fee_rate is None:
        flow_fee_rate = 12.0

    notification_time = event_start - timedelta(minutes=notification_minutes_before)
    baseline_start = notification_time - timedelta(hours=2)
    baseline_end = notification_time

    customer_records = validate_customer_records(records, customer_id)
    _ensure_full_window(customer_records, baseline_start, baseline_end, "通知前 2 小時")
    _ensure_full_window(customer_records, event_start, event_end, "事件時段")

    allowed_windows = [(baseline_start, baseline_end), (event_start, event_end)]

    baseline_records = filter_records_between(customer_records, baseline_start, baseline_end)
    baseline_kw = average_kw(baseline_records) or 0.0

    actual_records = filter_records_between(customer_records, event_start, event_end)
    actual_avg_kw = average_kw(actual_records) or 0.0

    actual_reduction_kw = max(baseline_kw - actual_avg_kw, 0.0)
    event_duration_hours = (event_end - event_start).total_seconds() / 3600.0

    capacity_denom = committed_capacity_kw if committed_capacity_kw is not None else contract_capacity_kw
    if capacity_denom <= 0:
        raise HTTPException(400, "committed_capacity_kw (或 contract_capacity_kw) 必須大於 0")

    exec_rate_pct = (Decimal(actual_reduction_kw) / Decimal(capacity_denom) * Decimal(100)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    exec_rate_rounded = min(float(exec_rate_pct) / 100.0, 1.0)

    target_load_kw = baseline_kw - committed_capacity_kw

    flow_reduction_amount = 0.0
    if exec_rate_rounded >= 0.7:
        flow_reduction_amount = actual_reduction_kw * event_duration_hours * flow_fee_rate

    extra_charge_amount = 0.0
    if exec_rate_rounded < 0.6:
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
        "target_load_kw": target_load_kw,
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
        target_load_kw=target_load_kw,
        detail=detail,
        method="guaranteed-reduction-v1",
    )


def compute_guaranteed_reduction_simple(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    notification_minutes_before: int,
    contract_capacity_kw: float,
    records: List[MeterRecord],
    committed_capacity_kw: float,
    dr_periods: Optional[List[DRPeriod]] = None,
):
    """
    與 compute_guaranteed_event 相同的基準/抑低/執行率計算，但不計算流動電費與違約金。
    """
    result = compute_guaranteed_event(
        customer_id=customer_id,
        event_start=event_start,
        event_end=event_end,
        notification_minutes_before=notification_minutes_before,
        contract_capacity_kw=contract_capacity_kw,
        committed_capacity_kw=committed_capacity_kw,
        records=records,
        basic_fee_rate=None,
        flow_fee_rate=None,
        dr_periods=dr_periods,
    )
    result.flow_reduction_amount = 0.0
    result.extra_charge_amount = 0.0
    result.detail["flow_reduction_amount"] = 0.0
    result.detail["extra_charge_amount"] = 0.0
    return result

def compute_guaranteed_reward(
    customer_id: str,
    notification_minutes_before: int,
    contract_capacity_kw: float,
    committed_capacity_kw: float,
    events: List[GuaranteedRewardEvent],
    records: List[MeterRecord],
    basic_fee_rate: Optional[float] = None,
    flow_fee_rate: Optional[float] = None,
    dr_periods: Optional[List[DRPeriod]] = None,
):
    if notification_minutes_before not in (30, 60, 120):
        raise HTTPException(400, "notification_minutes_before 必須為 30、60 或 120")

    if basic_fee_rate is None:
        if notification_minutes_before == 30:
            basic_fee_rate = 93.0
        elif notification_minutes_before == 60:
            basic_fee_rate = 84.0
        else:
            basic_fee_rate = 78.0
    if flow_fee_rate is None:
        flow_fee_rate = 12.0

    if not dr_periods:
        raise HTTPException(400, "dr_periods 必填")
    dr_period_ranges = parse_dr_periods(dr_periods)

    customer_records = validate_customer_records(records, customer_id)

    for ev in events:
        ev_start = to_taipei(ev.event_start)
        ev_end = to_taipei(ev.event_end)
        _validate_guaranteed_event_window(ev_start, ev_end)
        event_committed = ev.committed_capacity_kw if ev.committed_capacity_kw is not None else committed_capacity_kw
        _validate_guaranteed_capacity(contract_capacity_kw, event_committed)
        if not is_in_dr_period(ev_start.date(), dr_period_ranges):
            raise HTTPException(400, "事件日期未落在合約約定的抑低期間")
        baseline_end = ev_start - timedelta(minutes=notification_minutes_before)
        baseline_start = baseline_end - timedelta(hours=2)


    event_details: List[GuaranteedEventDetail] = []
    execution_rates: List[float] = []
    flow_total = 0.0
    extra_total = 0.0

    for ev in events:
        event_committed = ev.committed_capacity_kw
        if event_committed is None:
            event_committed = committed_capacity_kw
        ev_start = to_taipei(ev.event_start)
        ev_end = to_taipei(ev.event_end)
        baseline_end = ev_start - timedelta(minutes=notification_minutes_before)
        baseline_start = baseline_end - timedelta(hours=2)
        event_windows = [(baseline_start, baseline_end), (ev_start, ev_end)]
        event_records = _filter_records_in_windows(customer_records, event_windows)
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
            dr_periods=dr_periods,
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
                target_load_kw=result.target_load_kw,
                detail=result.detail,
            )
        )

    if not event_details:
        average_execution = 0.0
        reduction_ratio = 1.0
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
            method="guaranteed-reward-v1",
        )

    average_execution = sum(execution_rates) / len(execution_rates)

    if average_execution < 0.7:
        reduction_ratio = 0.0
    elif average_execution < 0.8:
        reduction_ratio = 0.6
    elif average_execution < 0.95:
        reduction_ratio = 0.8
    else:
        reduction_ratio = 1.0

    basic_reduction = contract_capacity_kw * basic_fee_rate * reduction_ratio
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
        method="guaranteed-reward-v1",
    )


# -------------------------
# 保證反應型：基準用電計算
# -------------------------
def compute_guaranteed_cbl(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    records: List[MeterRecord],
    notification_minutes_before: int,
    contract_capacity_kw: float,
    committed_capacity_kw: float,
    flow_fee_rate: Optional[float] = None,
    dr_periods: Optional[List[DRPeriod]] = None,
):
    if notification_minutes_before not in (30, 60, 120):
        raise HTTPException(400, "notification_minutes_before 必須為 30、60 或 120")
    if flow_fee_rate is None:
        flow_fee_rate = 12.0
    _validate_guaranteed_capacity(contract_capacity_kw, committed_capacity_kw)
    event_start = to_taipei(event_start)
    event_end = to_taipei(event_end)
    _validate_guaranteed_event_window(event_start, event_end)
    if not dr_periods:
        raise HTTPException(400, "dr_periods 必填")
    dr_period_ranges = parse_dr_periods(dr_periods)
    if not is_in_dr_period(event_start.date(), dr_period_ranges):
        raise HTTPException(400, "事件日期未落在合約約定的抑低期間")
    notification_time = event_start - timedelta(minutes=notification_minutes_before)
    baseline_start = notification_time - timedelta(hours=2)
    baseline_end = notification_time
    customer_records = validate_customer_records(records, customer_id)
    _ensure_full_window(customer_records, baseline_start, baseline_end, "通知前 2 小時")
    baseline_records = filter_records_between(customer_records, baseline_start, baseline_end)
    baseline_kw = average_kw(baseline_records) or 0.0
    target_load_kw = baseline_kw - committed_capacity_kw
    detail = {
        "baseline_start": baseline_start.isoformat(),
        "baseline_end": baseline_end.isoformat(),
        "baseline_kw": baseline_kw,
        "target_load_kw": target_load_kw,
        "committed_capacity_kw": committed_capacity_kw,
    }
    return GuaranteedCBLResponse(
        customer_id=customer_id,
        event_start=event_start,
        notification_minutes_before=notification_minutes_before,
        baseline_kw=baseline_kw,
        target_load_kw=target_load_kw,
        detail=detail,
        method="guaranteed-cbl-v1",
    )


# -------------------------
# 即時備轉：基準用電 (CBL)
# -------------------------
def build_spin_reserve_required_windows(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
) -> SpinReserveRequiredResponse:
    event_start = to_taipei(event_start)
    event_end = to_taipei(event_end)
    if event_end <= event_start:
        raise HTTPException(400, "event_end 必須晚於 event_start")

    baseline_start = event_start - timedelta(minutes=5)
    baseline_end = event_start
    windows = [
        RequiredWindow(label="baseline_5min", start=baseline_start, end=baseline_end, granularity_seconds=60)
    ]
    return SpinReserveRequiredResponse(customer_id=customer_id, windows=windows)


def compute_spin_reserve_cbl(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    records: List[MeterRecord],
    contract_capacity_kw: float,
    awarded_capacity_kw: float,
):
    event_start = to_taipei(event_start)
    event_end = to_taipei(event_end)
    if event_end <= event_start:
        raise HTTPException(400, "event_end 必須晚於 event_start")
    _validate_guaranteed_capacity(contract_capacity_kw, awarded_capacity_kw)

    baseline_start = event_start - timedelta(minutes=5)
    baseline_end = event_start

    customer_records = validate_customer_records_step(records, customer_id, step_minutes=1)
    _ensure_full_window_step(customer_records, baseline_start, baseline_end, "調度前 5 分鐘", step_minutes=1)

    baseline_records = filter_records_between(customer_records, baseline_start, baseline_end)
    baseline_kw = average_kw(baseline_records) or 0.0
    target_load_kw = baseline_kw - awarded_capacity_kw

    detail = {
        "baseline_start": baseline_start.isoformat(),
        "baseline_end": baseline_end.isoformat(),
        "baseline_kw": baseline_kw,
        "awarded_capacity_kw": awarded_capacity_kw,
        "contract_capacity_kw": contract_capacity_kw,
        "window_minutes": 5,
        "step_minutes": 1,
    }

    return SpinReserveCBLResponse(
        customer_id=customer_id,
        event_start=event_start,
        event_end=event_end,
        baseline_kw=baseline_kw,
        target_load_kw=target_load_kw,
        method="spin-reserve-cbl-v1",
        detail=detail,
    )


def build_day_select_required_windows(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    batch_time_tariff: bool = False,
    dr_periods: Optional[List[DRPeriod]] = None,
    min_baseline_days: int = 20,
) -> DaySelectRequiredPreResponse:
    event_start, event_end = _normalize_day_select_window(event_start, event_end, batch_time_tariff)
    if event_end <= event_start:
        raise HTTPException(400, "event_end 必須晚於 event_start")
    event_date = event_start.date()
    _validate_day_select_event_window(event_start, event_end, batch_time_tariff)
    if not dr_periods:
        raise HTTPException(400, "dr_periods 必填")
    dr_period_ranges = parse_dr_periods(dr_periods)
    if not is_in_dr_period(event_date, dr_period_ranges):
        raise HTTPException(400, "事件日期未落在合約約定的抑低期間")

    baseline_days: List[date] = []
    current_day = event_date - timedelta(days=1)
    boundary = previous_november_first(event_date)
    while len(baseline_days) < min_baseline_days and current_day >= boundary:
        if (
            not is_weekend(current_day)
            and not is_off_peak_day(current_day)
            and not is_in_dr_period(current_day, dr_period_ranges)
        ):
            baseline_days.append(current_day)
        current_day -= timedelta(days=1)
    if len(baseline_days) < min_baseline_days:
        raise HTTPException(400, f"資料不足以形成前 {min_baseline_days} 個合格日（已回溯至上一個 11/1），只找到 {len(baseline_days)} 日")

    required_days: List[RequiredDay] = []
    for d in baseline_days:
        required_days.append(RequiredDay(date=d, role="baseline", granularity_seconds=900))
    required_days.append(RequiredDay(date=event_date, role="event", granularity_seconds=900))

    return DaySelectRequiredPreResponse(
        customer_id=customer_id,
        baseline_days=sorted(baseline_days),
        required_days=required_days,
    )


def build_day_select_required_windows_post(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    batch_time_tariff: bool = False,
    dr_periods: Optional[List[DRPeriod]] = None,
    min_baseline_days: int = 20,
) -> DaySelectRequiredPostResponse:
    pre = build_day_select_required_windows(
        customer_id,
        event_start,
        event_end,
        batch_time_tariff,
        dr_periods,
        min_baseline_days,
    )
    return DaySelectRequiredPostResponse(customer_id=customer_id, required_days=pre.required_days)


def build_day_select_settlement_required(
    customer_id: str,
    events: List[DaySelectMonthlyEvent],
    dr_periods: Optional[List[DRPeriod]] = None,
    min_baseline_days: int = 20,
) -> DaySelectRequiredPostResponse:
    if not events:
        raise HTTPException(400, "events 不可為空")
    if not dr_periods:
        raise HTTPException(400, "dr_periods 必填")

    required_days: List[RequiredDay] = []
    for ev in events:
        per_event = build_day_select_required_windows(
            customer_id=customer_id,
            event_start=ev.event_start,
            event_end=ev.event_end,
            batch_time_tariff=ev.batch_time_tariff,
            dr_periods=dr_periods,
            min_baseline_days=min_baseline_days,
        )
        required_days.extend(per_event.required_days)

    # 去重並排序
    seen = set()
    unique_days: List[RequiredDay] = []
    for rd in sorted(required_days, key=lambda r: (r.date, r.role)):
        key = (rd.date, rd.role)
        if key in seen:
            continue
        seen.add(key)
        unique_days.append(rd)
    return DaySelectRequiredPostResponse(customer_id=customer_id, required_days=unique_days)


def build_guaranteed_settlement_required(
    customer_id: str,
    events: List[GuaranteedRewardEvent],
    dr_periods: Optional[List[DRPeriod]] = None,
) -> GuaranteedRequiredPostResponse:
    if not events:
        raise HTTPException(400, "events 不可為空")
    if not dr_periods:
        raise HTTPException(400, "dr_periods 必填")
    dr_period_ranges = parse_dr_periods(dr_periods)
    required_days: List[RequiredDay] = []
    for ev in events:
        ev_start = to_taipei(ev.event_start)
        ev_end = to_taipei(ev.event_end)
        _validate_guaranteed_event_window(ev_start, ev_end)
        if not is_in_dr_period(ev_start.date(), dr_period_ranges):
            raise HTTPException(400, "事件日期未落在合約約定的抑低期間")
        required_days.append(RequiredDay(date=ev_start.date(), role="event", granularity_seconds=900))
    # 去重
    seen = set()
    unique: List[RequiredDay] = []
    for rd in sorted(required_days, key=lambda r: (r.date, r.role)):
        key = (rd.date, rd.role)
        if key in seen:
            continue
        seen.add(key)
        unique.append(rd)
    return GuaranteedRequiredPostResponse(customer_id=customer_id, required_days=unique)


def build_guaranteed_required_windows(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    notification_minutes_before: int,
    dr_periods: Optional[List[DRPeriod]] = None,
) -> GuaranteedRequiredPreResponse:
    event_start = to_taipei(event_start)
    event_end = to_taipei(event_end)
    if event_end <= event_start:
        raise HTTPException(400, "event_end 必須晚於 event_start")
    _validate_guaranteed_event_window(event_start, event_end)
    if notification_minutes_before not in (30, 60, 120):
        raise HTTPException(400, "notification_minutes_before 必須為 30、60 或 120")
    if not dr_periods:
        raise HTTPException(400, "dr_periods 必填")
    dr_period_ranges = parse_dr_periods(dr_periods)
    if not is_in_dr_period(event_start.date(), dr_period_ranges):
        raise HTTPException(400, "事件日期未落在合約約定的抑低期間")
    required_days = [RequiredDay(date=event_start.date(), role="event", granularity_seconds=900)]
    return GuaranteedRequiredPreResponse(customer_id=customer_id, required_days=required_days)


def build_guaranteed_required_windows_post(
    customer_id: str,
    event_start: datetime,
    event_end: datetime,
    notification_minutes_before: int,
    dr_periods: Optional[List[DRPeriod]] = None,
) -> GuaranteedRequiredPostResponse:
    event_start = to_taipei(event_start)
    event_end = to_taipei(event_end)
    if event_end <= event_start:
        raise HTTPException(400, "event_end 必須晚於 event_start")
    _validate_guaranteed_event_window(event_start, event_end)
    if notification_minutes_before not in (30, 60, 120):
        raise HTTPException(400, "notification_minutes_before 必須為 30、60 或 120")
    if not dr_periods:
        raise HTTPException(400, "dr_periods 必填")
    dr_period_ranges = parse_dr_periods(dr_periods)
    if not is_in_dr_period(event_start.date(), dr_period_ranges):
        raise HTTPException(400, "事件日期未落在合約約定的抑低期間")
    required_days = [RequiredDay(date=event_start.date(), role="event", granularity_seconds=900)]
    return GuaranteedRequiredPostResponse(customer_id=customer_id, required_days=required_days)
