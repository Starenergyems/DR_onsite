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
    pre_resp = client.post("/dr/guaranteed/cbl/required-records", json=pre_req)
    assert pre_resp.status_code == 200
    pre_data = pre_resp.json()
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
    cbl_resp = client.post("/dr/guaranteed/cbl", json=cbl_req)
    assert cbl_resp.status_code == 200
    cbl_data = cbl_resp.json()
    assert "target_load_kw" in cbl_data
    assert cbl_data["target_load_kw"] < cbl_data["baseline_kw"]

    # required-records (reduction)
    post_req = pre_req
    post_resp = client.post("/dr/guaranteed/reduction/required-records", json=post_req)
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    assert len(post_data["required_days"]) == 1
    assert post_data["required_days"][0]["role"] == "event"

    # reduction
    reduction_req = {
        **pre_req,
        "records": records_payload,
        "contract_capacity_kw": contract_capacity_kw,
        "committed_capacity_kw": committed_capacity_kw,
    }
    reduction_resp = client.post("/dr/guaranteed/reduction", json=reduction_req)
    assert reduction_resp.status_code == 200
    reduction_data = reduction_resp.json()
    assert reduction_data["execution_rate"] > 0.6
    assert "target_load_kw" in reduction_data

    # settlement required
    settlement_required_req = {
        "customer_id": "G001",
        "events": [
            {"customer_id": "G001", "event_start": event_start_1.isoformat(), "event_end": event_end_1.isoformat()},
            {"customer_id": "G001", "event_start": event_start_2.isoformat(), "event_end": event_end_2.isoformat()},
        ],
        "dr_periods": dr_periods,
    }
    settle_required_resp = client.post("/dr/guaranteed/settlement/required-records", json=settlement_required_req)
    assert settle_required_resp.status_code == 200
    settle_required = settle_required_resp.json()
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
    settlement_resp = client.post("/dr/guaranteed/settlement", json=settlement_req)
    assert settlement_resp.status_code == 200
    settlement_data = settlement_resp.json()
    assert settlement_data["net_reward_amount"] >= 0
    assert settlement_data["event_details"]
    for ev in settlement_data["event_details"]:
        assert "target_load_kw" in ev
