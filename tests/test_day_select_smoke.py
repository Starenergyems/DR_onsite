import logging
from datetime import date, datetime, time, timedelta

import pytest
import pytz

from schemas import (
    DRPeriod,
    DaySelectMonthlyEvent,
    MeterRecord,
)
from services import (
    build_day_select_required_windows,
    build_day_select_required_windows_post,
    build_day_select_settlement_required,
    compute_day_select_cbl,
    compute_day_select_reduction,
    compute_day_select_settlement_monthly,
)


TZ = pytz.timezone("Asia/Taipei")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _preview_list(seq, n=5):
    """Return first/last n items, inserting ellipsis when truncated."""
    if len(seq) <= 2 * n:
        return list(seq)
    return list(seq[:n]) + ["..."] + list(seq[-n:])


def _generate_meter_records() -> list[MeterRecord]:
    """Generate full-day 15-min records covering all baseline + event dates."""
    start_d = date(2025, 6, 3)
    end_d = date(2025, 7, 9)  # includes day after last event for AF window
    event_days = {date(2025, 7, 1), date(2025, 7, 8)}
    records: list[MeterRecord] = []

    total_days = (end_d - start_d).days + 1
    for offset in range(total_days):
        day = start_d + timedelta(days=offset)
        for slot in range(96):  # 00:00 to 23:45 inclusive, 15-min steps
            ts_naive = datetime.combine(day, time(0, 0)) + timedelta(minutes=15 * slot)
            ts = TZ.localize(ts_naive)
            kw = 100.0
            if day in event_days and time(16, 0) < ts_naive.time() <= time(22, 0):
                kw = 20.0  # simulate reduction during the event window
            records.append(MeterRecord(customer_id="C001", timestamp=ts, kw=kw))
    # Full-day 15-min records (baseline + two events + day after last event for AF cross-day window).
    preview = _preview_list([f"{r.timestamp.isoformat()}|{r.kw}" for r in records], n=5)
    logger.info("generated %s records covering %s to %s; sample=%s", len(records), start_d, end_d, preview)
    return records


@pytest.fixture(scope="module")
def sample_records():
    return _generate_meter_records()


@pytest.fixture(scope="module")
def dr_periods():
    return [DRPeriod(start="2025-07", end="2025-10")]


def test_day_select_end_to_end_smoke(sample_records, dr_periods):
    event_start_1 = TZ.localize(datetime(2025, 7, 1, 16, 0))
    event_end_1 = TZ.localize(datetime(2025, 7, 1, 22, 0))
    event_start_2 = TZ.localize(datetime(2025, 7, 8, 16, 0))
    event_end_2 = TZ.localize(datetime(2025, 7, 8, 22, 0))
    contract_capacity_kw = 120.0
    committed_capacity_kw = 100.0

    pre_required = build_day_select_required_windows(
        customer_id="C001",
        event_start=event_start_1,
        event_end=event_end_1,
        batch_time_tariff=False,
        dr_periods=dr_periods,
        min_baseline_days=20,
    )
    # Expect 20 baseline days plus the event day.
    logger.info(
        "STEP 1 REQ /dr/day-select/cbl/required-records: start=%s end=%s dr_periods=%s",
        event_start_1,
        event_end_1,
        dr_periods,
    )
    full_required_pre = [f"{rd.date}|{rd.role}" for rd in pre_required.required_days]
    logger.info(
        "STEP 1 RESP required_pre: baseline=%s, event=%s, required_days=%s",
        len(pre_required.baseline_days),
        event_start_1.date(),
        full_required_pre,
    )
    assert len(pre_required.baseline_days) == 20
    assert any(rd.date == event_start_1.date() and rd.role == "event" for rd in pre_required.required_days)

    cbl_resp = compute_day_select_cbl(
        customer_id="C001",
        event_start=event_start_1,
        event_end=event_end_1,
        records=sample_records,
        batch_time_tariff=False,
        contract_capacity_kw=contract_capacity_kw,
        committed_capacity_kw=committed_capacity_kw,
        dr_periods=dr_periods,
    )
    # Synthetic load keeps CBL near 100 kW.
    logger.info("STEP 2 data prepared: full-day records for 20 baselines + event day (synthetic)")
    logger.info(
        "STEP 3 REQ /dr/day-select/cbl: start=%s end=%s batch_time_tariff=%s contract=%s dr_periods=%s records=%s preview=%s",
        event_start_1,
        event_end_1,
        False,
        contract_capacity_kw,
        dr_periods,
        len(sample_records),
        _preview_list([f"{r.timestamp.isoformat()}|{r.kw}" for r in sample_records], n=5),
    )
    logger.info(
        "STEP 3 RESP CBL: cbl_kw=%.3f, target_load_kw=%.3f, baseline_days=%s, baseline_source_days=%s, detail=%s",
        cbl_resp.cbl_kw,
        cbl_resp.target_load_kw,
        len(cbl_resp.baseline_source_days),
        cbl_resp.baseline_source_days,
        cbl_resp.detail,
    )
    assert len(cbl_resp.baseline_source_days) == 20
    assert cbl_resp.cbl_kw == pytest.approx(100.0, rel=1e-3)
    assert cbl_resp.target_load_kw == pytest.approx(cbl_resp.cbl_kw - committed_capacity_kw, rel=1e-3)

    post_required = build_day_select_required_windows_post(
        customer_id="C001",
        event_start=event_start_1,
        event_end=event_end_1,
        batch_time_tariff=False,
        dr_periods=dr_periods,
        min_baseline_days=20,
    )
    # Post required should include baseline + event day (20 + 1 = 21).
    logger.info(
        "STEP 4 REQ /dr/day-select/reduction/required-records: start=%s end=%s batch_time_tariff=%s dr_periods=%s min_baseline_days=%s",
        event_start_1,
        event_end_1,
        False,
        dr_periods,
        20,
    )
    logger.info(
        "STEP 4 RESP required_post: count=%s preview=%s",
        len(post_required.required_days),
        _preview_list([f"{rd.date}|{rd.role}" for rd in post_required.required_days]),
    )
    logger.info(
        "STEP 4 RESP required_post full required_days=%s",
        [f"{rd.date}|{rd.role}" for rd in post_required.required_days],
    )
    assert len(post_required.required_days) == len(pre_required.required_days)

    reduction_resp = compute_day_select_reduction(
        customer_id="C001",
        event_start=event_start_1,
        event_end=event_end_1,
        records=sample_records,
        batch_time_tariff=False,
        contract_capacity_kw=contract_capacity_kw,
        committed_capacity_kw=committed_capacity_kw,
        dr_periods=dr_periods,
    )
    # Synthetic reduction: ~80 kW drop, execution rate around 0.8.
    logger.info("STEP 5 data prepared: baseline + event day full-day records (synthetic)")
    logger.info(
        "STEP 6 REQ /dr/day-select/reduction: start=%s end=%s batch_time_tariff=%s contract=%s committed=%s dr_periods=%s records=%s preview=%s",
        event_start_1,
        event_end_1,
        False,
        contract_capacity_kw,
        committed_capacity_kw,
        dr_periods,
        len(sample_records),
        _preview_list([f"{r.timestamp.isoformat()}|{r.kw}" for r in sample_records], n=5),
    )
    logger.info(
        "STEP 6 RESP reduction: cbl_kw=%.3f, actual_avg_kw=%.3f, actual_reduction_kw=%.3f, execution_rate=%.3f, reduction_ratio=%.3f, reward_ntd=%.2f",
        reduction_resp.cbl_kw,
        reduction_resp.actual_avg_kw,
        reduction_resp.actual_reduction_kw,
        reduction_resp.execution_rate,
        reduction_resp.reduction_ratio,
        reduction_resp.reward_ntd,
    )
    logger.info("STEP 6 RESP reduction detail=%s", reduction_resp.detail)
    assert reduction_resp.actual_reduction_kw > 0
    assert reduction_resp.reward_ntd > 0
    assert reduction_resp.execution_rate >= 0.8

    events = [
        DaySelectMonthlyEvent(event_start=event_start_1, event_end=event_end_1, batch_time_tariff=False),
        DaySelectMonthlyEvent(event_start=event_start_2, event_end=event_end_2, batch_time_tariff=False),
    ]
    settlement_required = build_day_select_settlement_required(
        customer_id="C001",
        events=events,
        dr_periods=dr_periods,
        min_baseline_days=20,
    )
    # Monthly required = 20 baselines + 2 event days.
    logger.info(
        "STEP 7 REQ /dr/day-select/settlement/required-records: events=%s dr_periods=%s min_baseline_days=%s",
        [(ev.event_start, ev.event_end) for ev in events],
        dr_periods,
        20,
    )
    logger.info(
        "STEP 7 RESP settlement_required: baseline=%s, events=%s preview=%s",
        len([rd for rd in settlement_required.required_days if rd.role == "baseline"]),
        len([rd for rd in settlement_required.required_days if rd.role == "event"]),
        _preview_list([f"{rd.date}|{rd.role}" for rd in settlement_required.required_days]),
    )
    logger.info(
        "STEP 7 RESP settlement_required full required_days=%s",
        [f"{rd.date}|{rd.role}" for rd in settlement_required.required_days],
    )
    assert len([rd for rd in settlement_required.required_days if rd.role == "baseline"]) == 20
    assert len([rd for rd in settlement_required.required_days if rd.role == "event"]) == 2

    logger.info("STEP 8 data prepared: baseline + two event days full-day records (synthetic)")

    settlement_resp = compute_day_select_settlement_monthly(
        customer_id="C001",
        contract_capacity_kw=contract_capacity_kw,
        committed_capacity_kw=committed_capacity_kw,
        dr_periods=dr_periods,
        records=sample_records,
        events=events,
        min_baseline_days=20,
    )
    # Monthly totals should equal sum of per-event rewards/reductions.
    logger.info(
        "STEP 9 REQ /dr/day-select/settlement: records=%s contract=%s committed=%s events=%s dr_periods=%s min_baseline_days=%s",
        len(sample_records),
        contract_capacity_kw,
        committed_capacity_kw,
        [(ev.event_start, ev.event_end) for ev in events],
        dr_periods,
        20,
    )
    logger.info(
        "STEP 9 RESP settlement: total_reward=%.2f, total_actual_reduction_kwh=%.3f, per_event_preview=%s",
        settlement_resp.total_reward_ntd,
        settlement_resp.total_actual_reduction_kwh,
        _preview_list(
            [
                f"{ev.event_start.isoformat()}|cbl={ev.cbl_kw:.1f}|actual_avg={ev.actual_avg_kw:.1f}|reward={ev.reward_ntd:.2f}"
                for ev in settlement_resp.events
            ],
            n=2,
        ),
    )
    logger.info(
        "STEP 9 RESP settlement full events detail=%s",
        [
            {
                "event_start": ev.event_start,
                "event_end": ev.event_end,
                "cbl_kw": ev.cbl_kw,
                "actual_avg_kw": ev.actual_avg_kw,
                "actual_reduction_kw": ev.actual_reduction_kw,
                "execution_rate": ev.execution_rate,
                "reduction_ratio": ev.reduction_ratio,
                "reward_ntd": ev.reward_ntd,
                "detail": ev.detail,
            }
            for ev in settlement_resp.events
        ],
    )
    assert len(settlement_resp.events) == 2
    assert settlement_resp.total_reward_ntd > 0
    assert settlement_resp.total_reward_ntd == pytest.approx(
        sum(ev.reward_ntd for ev in settlement_resp.events)
    )
    assert settlement_resp.total_actual_reduction_kwh > 0
