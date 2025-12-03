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
        "bid_capacity_kw": 2000.0,
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


def test_spin_reserve_reduction_and_settlement(client):
    event_start = TZ.localize(datetime(2025, 7, 3, 14, 0))
    event_end = event_start + timedelta(hours=1)

    required_req = {
        "customer_id": "SR001",
        "event_start": event_start.isoformat(),
        "event_end": event_end.isoformat(),
    }
    logger.info("REQ /dr/spin-reserve/reduction/required-records: %s", required_req)
    resp = client.post("/dr/spin-reserve/reduction/required-records", json=required_req)
    assert resp.status_code == 200
    required_data = resp.json()
    assert required_data["windows"]

    records_payload = _generate_minute_records(
        start_dt=event_start - timedelta(minutes=10),
        end_dt=event_end + timedelta(minutes=5),
        event_start=event_start,
    )

    reduction_req = {
        **required_req,
        "awarded_capacity_kw": 1000.0,
        "efficiency_level": 1,
        "is_dispatched": True,
        "capacity_price_per_kw": 0.0,
        "energy_price_per_kwh": 4.0,
        "records": records_payload,
    }
    logger.info(
        "REQ /dr/spin-reserve/reduction: payload=%s records=%s",
        {k: v for k, v in reduction_req.items() if k != "records"},
        len(records_payload),
    )
    red_resp = client.post("/dr/spin-reserve/reduction", json=reduction_req)
    assert red_resp.status_code == 200
    red_data = red_resp.json()
    logger.info("RESP /dr/spin-reserve/reduction: %s", red_data)
    assert red_data["baseline_kw"] == pytest.approx(1500.0, rel=0.01)
    assert red_data["actual_reduction_kw"] > 0
    assert red_data["total_fee"] >= 0

    # Settlement required
    settlement_required_req = {
        "customer_id": "SR001",
        "events": [
            {
                "event_start": event_start.isoformat(),
                "event_end": event_end.isoformat(),
                "awarded_capacity_kw": 1000.0,
                "efficiency_level": 1,
                "is_dispatched": True,
            }
        ],
    }
    sett_req_resp = client.post("/dr/spin-reserve/settlement/required-records", json=settlement_required_req)
    assert sett_req_resp.status_code == 200
    sett_req_data = sett_req_resp.json()
    assert sett_req_data["windows"]

    settlement_req = {
        **settlement_required_req,
        "events": [
            {
                "event_start": event_start.isoformat(),
                "event_end": event_end.isoformat(),
                "awarded_capacity_kw": 1000.0,
                "efficiency_level": 1,
                "is_dispatched": True,
                "capacity_price_per_kw": 0.0,
                "energy_price_per_kwh": 4.0,
            }
        ],
        "records": records_payload,
    }
    logger.info(
        "REQ /dr/spin-reserve/settlement: payload=%s records=%s",
        {k: v for k, v in settlement_req.items() if k != "records"},
        len(records_payload),
    )
    sett_resp = client.post("/dr/spin-reserve/settlement", json=settlement_req)
    assert sett_resp.status_code == 200
    sett_data = sett_resp.json()
    logger.info("RESP /dr/spin-reserve/settlement: %s", sett_data)
    assert sett_data["total_fee"] >= 0
    assert sett_data["events"]


def test_spin_reserve_no_dispatch(client):
    """
    情境：得標但未接到調度指令，視為待命。
    驗證 reduction 仍可計算出 baseline，實際抑低為 0，執行率 0，SQI -1，電能費 0。
    """
    event_start = TZ.localize(datetime(2025, 7, 4, 14, 0))
    event_end = event_start + timedelta(hours=1)

    # 建立全程未抑低的 1 分鐘資料（1500 kW）
    records = []
    cursor = event_start - timedelta(minutes=10)
    while cursor <= event_end + timedelta(minutes=5):
        records.append(
            {
                "customer_id": "SR001",
                "timestamp": cursor.isoformat(),
                "kw": 1500.0,
            }
        )
        cursor += timedelta(minutes=1)

    required_req = {
        "customer_id": "SR001",
        "event_start": event_start.isoformat(),
        "event_end": event_end.isoformat(),
    }
    logger.info("REQ /dr/spin-reserve/reduction/required-records (no-dispatch): %s", required_req)
    resp = client.post("/dr/spin-reserve/reduction/required-records", json=required_req)
    assert resp.status_code == 200
    logger.info("RESP /dr/spin-reserve/reduction/required-records (no-dispatch): %s", resp.json())

    reduction_req = {
        **required_req,
        "awarded_capacity_kw": 1000.0,
        "efficiency_level": 1,
        "capacity_price_per_kw": 0.0,
        # 不提供 energy_price，使用預設估值
        "is_dispatched": False,
        "records": records,
    }
    logger.info(
        "REQ /dr/spin-reserve/reduction (no-dispatch): payload=%s records=%s",
        {k: v for k, v in reduction_req.items() if k != "records"},
        len(records),
    )
    red_resp = client.post("/dr/spin-reserve/reduction", json=reduction_req)
    assert red_resp.status_code == 200
    data = red_resp.json()
    logger.info("RESP /dr/spin-reserve/reduction (no-dispatch): %s", data)
    assert data["baseline_kw"] == pytest.approx(1500.0, rel=0.01)
    assert data["actual_reduction_kw"] == pytest.approx(0.0, rel=0.01)
    assert data["execution_rate"] == pytest.approx(0.0, rel=0.01)
    assert data["energy_fee"] == pytest.approx(0.0, rel=0.01)
