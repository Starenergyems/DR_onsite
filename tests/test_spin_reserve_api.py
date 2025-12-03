import logging
from datetime import datetime, timedelta

import pytest
import pytz
from fastapi.testclient import TestClient

from main import app


TZ = pytz.timezone("Asia/Taipei")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _generate_minute_records(start_dt: datetime, end_dt: datetime, event_start: datetime, base_kw=1500.0, event_kw=900.0):
    records = []
    cursor = start_dt
    while cursor <= end_dt:
        kw = base_kw if cursor <= event_start else event_kw
        records.append(
            {
                "customer_id": "SR001",
                "timestamp": cursor.isoformat(),
                "kw": kw,
            }
        )
        cursor += timedelta(minutes=1)
    logger.info("generated %s minute-level records; first=%s last=%s", len(records), records[0]["timestamp"], records[-1]["timestamp"])
    return records


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_spin_reserve_cbl_flow(client):
    event_start = TZ.localize(datetime(2025, 7, 2, 14, 0))
    event_end = event_start + timedelta(hours=1)

    required_req = {
        "customer_id": "SR001",
        "event_start": event_start.isoformat(),
        "event_end": event_end.isoformat(),
    }

    logger.info("REQ /dr/spin-reserve/cbl/required-records: %s", required_req)
    resp = client.post("/dr/spin-reserve/cbl/required-records", json=required_req)
    assert resp.status_code == 200
    required_data = resp.json()
    logger.info("RESP /dr/spin-reserve/cbl/required-records: %s", required_data)
    assert required_data["windows"], "expected windows payload"
    assert len(required_data["windows"]) == 1
    baseline_window = required_data["windows"][0]
    assert baseline_window["label"] == "baseline_5min"
    assert baseline_window["start"].endswith("13:55:00+08:00")
    assert baseline_window["end"].endswith("14:00:00+08:00")
    assert baseline_window.get("granularity_seconds") == 60

    records_payload = _generate_minute_records(
        start_dt=event_start - timedelta(minutes=10),
        end_dt=event_end + timedelta(minutes=5),
        event_start=event_start,
    )

    cbl_req = {
        **required_req,
        "records": records_payload,
        "contract_capacity_kw": 2000.0,
        "awarded_capacity_kw": 1200.0,
    }

    logger.info(
        "REQ /dr/spin-reserve/cbl: payload=%s records=%s",
        {k: v for k, v in cbl_req.items() if k != "records"},
        len(records_payload),
    )
    cbl_resp = client.post("/dr/spin-reserve/cbl", json=cbl_req)
    assert cbl_resp.status_code == 200
    data = cbl_resp.json()
    logger.info("RESP /dr/spin-reserve/cbl: %s", data)
    assert data["baseline_kw"] == pytest.approx(1500.0, rel=0.01)
    assert data["target_load_kw"] == pytest.approx(data["baseline_kw"] - 1200.0, rel=0.01)
    assert data["method"].startswith("spin-reserve-cbl")
