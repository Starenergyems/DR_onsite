import logging
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


def _generate_full_day_records(days: list[date], event_hours=(time(16, 0), time(18, 0))) -> list[MeterRecord]:
    """Generate full-day 15-min records for each day; drop load during event hours."""
    records: list[MeterRecord] = []
    event_days = set(days)
    for d in event_days:
        for slot in range(96):  # 00:00 to 23:45
            ts_naive = datetime.combine(d, time(0, 0)) + timedelta(minutes=15 * slot)
            ts = TZ.localize(ts_naive)
            kw = 1500.0
            if event_hours[0] < ts_naive.time() <= event_hours[1]:
                kw = 500.0  # simulate reduction during the event window
            records.append(MeterRecord(customer_id="G001", timestamp=ts, kw=kw))
    preview = _preview_list([f"{r.timestamp.isoformat()}|{r.kw}" for r in records], n=5)
    logger.info("generated %s records for days=%s; sample=%s", len(records), sorted(event_days), preview)
    return records


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def event_dates():
    return [date(2025, 7, 8), date(2025, 7, 15)]


@pytest.fixture(scope="module")
def records_payload(event_dates):
    recs = _generate_full_day_records(event_dates)
    return [{"customer_id": r.customer_id, "timestamp": r.timestamp.isoformat(), "kw": r.kw} for r in recs]


def test_guaranteed_flow_required_and_settlement(client, event_dates, records_payload):
    event_start_1 = TZ.localize(datetime.combine(event_dates[0], time(16, 0)))
    event_end_1 = TZ.localize(datetime.combine(event_dates[0], time(18, 0)))
    event_start_2 = TZ.localize(datetime.combine(event_dates[1], time(16, 0)))
    event_end_2 = TZ.localize(datetime.combine(event_dates[1], time(18, 0)))
    dr_periods = [{"start": "2025-07-01", "end": "2025-07-31"}]
    contract_capacity_kw = 2000.0
    committed_capacity_kw = 1200.0
    notification_minutes_before = 60

    # required-records (CBL)
    pre_req = {
        "customer_id": "G001",
        "event_start": event_start_1.isoformat(),
        "event_end": event_end_1.isoformat(),
        "notification_minutes_before": notification_minutes_before,
        "dr_periods": dr_periods,
    }
    logger.info("STEP 1 REQ /dr/guaranteed/cbl/required-records: %s", pre_req)
    pre_resp = client.post("/dr/guaranteed/cbl/required-records", json=pre_req)
    assert pre_resp.status_code == 200
    pre_data = pre_resp.json()
    logger.info(
        "STEP 1 RESP required_pre: event_day=%s required_days=%s",
        event_start_1.date(),
        [f"{rd['date']}|{rd['role']}" for rd in pre_data["required_days"]],
    )
    assert "windows" not in pre_data
    assert len(pre_data["required_days"]) == 1
    assert pre_data["required_days"][0]["role"] == "event"

    # CBL
    cbl_req = {
        **pre_req,
        "records": records_payload,
        "contract_capacity_kw": contract_capacity_kw,
        "committed_capacity_kw": committed_capacity_kw,
    }
    logger.info("STEP 3 REQ /dr/guaranteed/cbl: %s ...records=%s", {k: v for k, v in cbl_req.items() if k != "records"}, len(records_payload))
    cbl_resp = client.post("/dr/guaranteed/cbl", json=cbl_req)
    assert cbl_resp.status_code == 200
    cbl_data = cbl_resp.json()
    logger.info(
        "STEP 3 RESP CBL: baseline_kw=%.3f target_load_kw=%.3f detail=%s",
        cbl_data["baseline_kw"],
        cbl_data["target_load_kw"],
        cbl_data["detail"],
    )
    assert "target_load_kw" in cbl_data
    assert cbl_data["target_load_kw"] < cbl_data["baseline_kw"]

    # required-records (reduction)
    post_req = pre_req
    logger.info("STEP 4 REQ /dr/guaranteed/reduction/required-records: %s", post_req)
    post_resp = client.post("/dr/guaranteed/reduction/required-records", json=post_req)
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    logger.info(
        "STEP 4 RESP required_post: count=%s preview=%s",
        len(post_data["required_days"]),
        _preview_list([f"{rd['date']}|{rd['role']}" for rd in post_data["required_days"]]),
    )
    assert len(post_data["required_days"]) == 1
    assert post_data["required_days"][0]["role"] == "event"

    # reduction
    reduction_req = {
        **pre_req,
        "records": records_payload,
        "contract_capacity_kw": contract_capacity_kw,
        "committed_capacity_kw": committed_capacity_kw,
    }
    logger.info(
        "STEP 6 REQ /dr/guaranteed/reduction: %s ...records=%s",
        {k: v for k, v in reduction_req.items() if k != "records"},
        len(records_payload),
    )
    reduction_resp = client.post("/dr/guaranteed/reduction", json=reduction_req)
    assert reduction_resp.status_code == 200
    reduction_data = reduction_resp.json()
    logger.info(
        "STEP 6 RESP reduction: baseline_kw=%.3f target_load_kw=%.3f actual_reduction_kw=%.3f exec_rate=%.3f flow_reduction=%.2f extra=%.2f detail=%s",
        reduction_data["baseline_kw"],
        reduction_data["target_load_kw"],
        reduction_data["actual_reduction_kw"],
        reduction_data["execution_rate"],
        reduction_data["flow_reduction_amount"],
        reduction_data["extra_charge_amount"],
        reduction_data["detail"],
    )
    assert reduction_data["execution_rate"] > 0.6
    assert "target_load_kw" in reduction_data
    assert reduction_data["flow_reduction_amount"] >= 0
    assert reduction_data["extra_charge_amount"] >= 0

    # settlement required
    settlement_required_req = {
        "customer_id": "G001",
        "events": [
            {"customer_id": "G001", "event_start": event_start_1.isoformat(), "event_end": event_end_1.isoformat()},
            {"customer_id": "G001", "event_start": event_start_2.isoformat(), "event_end": event_end_2.isoformat()},
        ],
        "dr_periods": dr_periods,
    }
    logger.info("STEP 7 REQ /dr/guaranteed/settlement/required-records: %s", settlement_required_req)
    settle_required_resp = client.post("/dr/guaranteed/settlement/required-records", json=settlement_required_req)
    assert settle_required_resp.status_code == 200
    settle_required = settle_required_resp.json()
    logger.info(
        "STEP 7 RESP settlement_required: events=%s required_days=%s",
        len(settle_required["required_days"]),
        _preview_list([f"{rd['date']}|{rd['role']}" for rd in settle_required["required_days"]]),
    )
    assert len(settle_required["required_days"]) == 2
    assert all(rd["role"] == "event" for rd in settle_required["required_days"])

    # settlement (reward)
    settlement_req = {
        "customer_id": "G001",
        "notification_minutes_before": notification_minutes_before,
        "contract_capacity_kw": contract_capacity_kw,
        "committed_capacity_kw": committed_capacity_kw,
        "events": settlement_required_req["events"],
        "records": records_payload,
        "dr_periods": dr_periods,
    }
    logger.info(
        "STEP 9 REQ /dr/guaranteed/settlement: %s ...records=%s",
        {k: v for k, v in settlement_req.items() if k != "records"},
        len(records_payload),
    )
    settlement_resp = client.post("/dr/guaranteed/settlement", json=settlement_req)
    assert settlement_resp.status_code == 200
    settlement_data = settlement_resp.json()
    logger.info(
        "STEP 9 RESP settlement: net_reward=%.2f flow_total=%.2f extra_total=%.2f avg_exec=%.3f",
        settlement_data["net_reward_amount"],
        settlement_data["flow_reduction_total_amount"],
        settlement_data["extra_charge_total_amount"],
        settlement_data["average_execution_rate"],
    )
    assert settlement_data["net_reward_amount"] >= 0
    assert settlement_data["event_details"]
    for ev in settlement_data["event_details"]:
        assert "target_load_kw" in ev


def test_guaranteed_no_notification_month_returns_basic_fee_only(client):
    required_resp = client.post(
        "/dr/guaranteed/settlement/required-records",
        json={
            "customer_id": "G001",
            "events": [],
            "dr_periods": [{"start": "2025-07-01", "end": "2025-07-31"}],
        },
    )
    assert required_resp.status_code == 200
    assert required_resp.json()["required_days"] == []

    settlement_resp = client.post(
        "/dr/guaranteed/settlement",
        json={
            "customer_id": "G001",
            "notification_minutes_before": 60,
            "contract_capacity_kw": 2000.0,
            "committed_capacity_kw": 1200.0,
            "events": [],
            "records": [],
            "dr_periods": [{"start": "2025-07-01", "end": "2025-07-31"}],
        },
    )
    assert settlement_resp.status_code == 200
    data = settlement_resp.json()
    assert data["average_execution_rate"] == 0.0
    assert data["reduction_ratio"] == 1.0
    assert data["basic_fee_rate"] == 84.0
    assert data["basic_reduction_amount"] == 168000.0
    assert data["flow_reduction_total_amount"] == 0.0
    assert data["extra_charge_total_amount"] == 0.0
    assert data["net_reward_amount"] == 168000.0
    assert data["event_details"] == []
