import logging
import math
from datetime import date, datetime, time, timedelta

import pytest
import pytz
from fastapi.testclient import TestClient

from main import app
from schemas import MeterRecord

TZ = pytz.timezone("Asia/Taipei")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _preview_list(seq, n=5):
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
    preview = _preview_list([f"{r.timestamp.isoformat()}|{r.kw}" for r in records], n=5)
    logger.info("generated %s records covering %s to %s; sample=%s", len(records), start_d, end_d, preview)
    return records


@pytest.fixture(scope="module")
def sample_records():
    return _generate_meter_records()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_day_select_api_flow(client, sample_records):
    event_start_1 = TZ.localize(datetime(2025, 7, 1, 16, 0))
    event_end_1 = TZ.localize(datetime(2025, 7, 1, 22, 0))
    event_start_2 = TZ.localize(datetime(2025, 7, 8, 16, 0))
    event_end_2 = TZ.localize(datetime(2025, 7, 8, 22, 0))
    dr_periods = [{"start": "2025-07", "end": "2025-10"}]
    contract_capacity_kw = 120.0
    committed_capacity_kw = 100.0

    records_payload = [
        {"customer_id": r.customer_id, "timestamp": r.timestamp.isoformat(), "kw": r.kw} for r in sample_records
    ]

    # STEP 1: cbl/required-records
    pre_req = {
        "customer_id": "C001",
        "event_start": event_start_1.isoformat(),
        "event_end": event_end_1.isoformat(),
        "batch_time_tariff": False,
        "dr_periods": dr_periods,
        "min_baseline_days": 20,
    }
    logger.info("STEP 1 REQ /dr/day-select/cbl/required-records: %s", pre_req)
    pre_resp = client.post("/dr/day-select/cbl/required-records", json=pre_req)
    assert pre_resp.status_code == 200
    pre_data = pre_resp.json()
    logger.info(
        "STEP 1 RESP required_pre: baseline=%s event_day=%s required_days=%s",
        len(pre_data["baseline_days"]),
        event_start_1.date(),
        [f"{rd['date']}|{rd['role']}" for rd in pre_data["required_days"]],
    )
    assert len(pre_data["baseline_days"]) == 20
    assert any(rd["role"] == "event" for rd in pre_data["required_days"])

    # STEP 3: cbl
    cbl_req = {
        "customer_id": "C001",
        "event_start": event_start_1.isoformat(),
        "event_end": event_end_1.isoformat(),
        "batch_time_tariff": False,
        "assumed_af_kw": None,
        "records": records_payload,
        "contract_capacity_kw": contract_capacity_kw,
        "committed_capacity_kw": committed_capacity_kw,
        "dr_periods": dr_periods,
    }
    logger.info("STEP 3 REQ /dr/day-select/cbl: %s ...records=%s", {k: v for k, v in cbl_req.items() if k != "records"}, len(records_payload))
    cbl_resp = client.post("/dr/day-select/cbl", json=cbl_req)
    assert cbl_resp.status_code == 200
    cbl_data = cbl_resp.json()
    logger.info(
        "STEP 3 RESP CBL: cbl_kw=%.3f target_load_kw=%.3f baseline_days=%s detail=%s",
        cbl_data["cbl_kw"],
        cbl_data["target_load_kw"],
        len(cbl_data["baseline_source_days"]),
        cbl_data["detail"],
    )
    assert math.isclose(cbl_data["cbl_kw"], 100.0, rel_tol=1e-3)
    assert math.isclose(cbl_data["target_load_kw"], 0.0, rel_tol=1e-3)
    assert len(cbl_data["baseline_source_days"]) == 20

    # STEP 4: reduction/required-records
    post_req = {
        "customer_id": "C001",
        "event_start": event_start_1.isoformat(),
        "event_end": event_end_1.isoformat(),
        "batch_time_tariff": False,
        "dr_periods": dr_periods,
        "min_baseline_days": 20,
    }
    logger.info("STEP 4 REQ /dr/day-select/reduction/required-records: %s", post_req)
    post_resp = client.post(
        "/dr/day-select/reduction/required-records",
        json=post_req,
    )
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    logger.info(
        "STEP 4 RESP required_post: count=%s preview=%s",
        len(post_data["required_days"]),
        _preview_list([f"{rd['date']}|{rd['role']}" for rd in post_data["required_days"]]),
    )
    assert len(post_data["required_days"]) == len(pre_data["required_days"])

    # STEP 6: reduction
    reduction_req = {
        "customer_id": "C001",
        "event_start": event_start_1.isoformat(),
        "event_end": event_end_1.isoformat(),
        "batch_time_tariff": False,
        "assumed_af_kw": None,
        "records": records_payload,
        "contract_capacity_kw": contract_capacity_kw,
        "committed_capacity_kw": committed_capacity_kw,
        "dr_periods": dr_periods,
    }
    logger.info(
        "STEP 6 REQ /dr/day-select/reduction: %s ...records=%s",
        {k: v for k, v in reduction_req.items() if k != "records"},
        len(records_payload),
    )
    reduction_resp = client.post("/dr/day-select/reduction", json=reduction_req)
    assert reduction_resp.status_code == 200
    reduction_data = reduction_resp.json()
    logger.info(
        "STEP 6 RESP reduction: cbl_kw=%.3f target_load_kw=%.3f actual_avg_kw=%.3f reduction_kw=%.3f exec_rate=%.3f reward=%.2f detail=%s",
        reduction_data["cbl_kw"],
        reduction_data["target_load_kw"],
        reduction_data["actual_avg_kw"],
        reduction_data["actual_reduction_kw"],
        reduction_data.get("execution_rate") or 0.0,
        reduction_data["reward_ntd"],
        reduction_data["detail"],
    )
    assert reduction_data["reward_ntd"] > 0
    assert math.isclose(reduction_data["target_load_kw"], 0.0, rel_tol=1e-3)
    assert reduction_data["execution_rate"] >= 0.8

    # STEP 7: settlement/required-records
    events_payload = [
        {
            "event_start": event_start_1.isoformat(),
            "event_end": event_end_1.isoformat(),
            "batch_time_tariff": False,
        },
        {
            "event_start": event_start_2.isoformat(),
            "event_end": event_end_2.isoformat(),
            "batch_time_tariff": False,
        },
    ]
    settle_req = {
        "customer_id": "C001",
        "events": events_payload,
        "dr_periods": dr_periods,
        "min_baseline_days": 20,
    }
    logger.info("STEP 7 REQ /dr/day-select/settlement/required-records: %s", settle_req)
    settle_required_resp = client.post("/dr/day-select/settlement/required-records", json=settle_req)
    assert settle_required_resp.status_code == 200
    settle_required_data = settle_required_resp.json()
    logger.info(
        "STEP 7 RESP settlement_required: baseline=%s events=%s required_days=%s",
        len([rd for rd in settle_required_data["required_days"] if rd["role"] == "baseline"]),
        len([rd for rd in settle_required_data["required_days"] if rd["role"] == "event"]),
        _preview_list([f"{rd['date']}|{rd['role']}" for rd in settle_required_data["required_days"]]),
    )
    assert len([rd for rd in settle_required_data["required_days"] if rd["role"] == "baseline"]) == 20
    assert len([rd for rd in settle_required_data["required_days"] if rd["role"] == "event"]) == 2

    # STEP 9: settlement compute
    settlement_req = {
        "customer_id": "C001",
        "contract_capacity_kw": contract_capacity_kw,
        "committed_capacity_kw": committed_capacity_kw,
        "dr_periods": dr_periods,
        "records": records_payload,
        "events": events_payload,
    }
    logger.info(
        "STEP 9 REQ /dr/day-select/settlement: %s ...records=%s",
        {k: v for k, v in settlement_req.items() if k != "records"},
        len(records_payload),
    )
    settlement_resp = client.post("/dr/day-select/settlement", json=settlement_req)
    assert settlement_resp.status_code == 200
    settlement_data = settlement_resp.json()
    logger.info(
        "STEP 9 RESP settlement: total_reward=%.2f total_reduction_kwh=%.2f",
        settlement_data["total_reward_ntd"],
        settlement_data["total_actual_reduction_kwh"],
    )
    assert settlement_data["total_reward_ntd"] > 0
    for ev in settlement_data["events"]:
        assert "target_load_kw" in ev
        assert math.isclose(ev["target_load_kw"], ev["cbl_kw"] - committed_capacity_kw, rel_tol=1e-3)
