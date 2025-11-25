import json
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException

from schemas import (
    DaySelectCBLRequest,
    DaySelectRewardRequest,
    DaySelectReductionRequest,
    DaySelectRequiredRequest,
    GuaranteedCBLRequest,
    GuaranteedEventRequest,
    GuaranteedRewardRequest,
    GuaranteedRequiredRequest,
)
from services import (
    compute_day_select_cbl,
    compute_day_select_reduction,
    compute_day_select_reward,
    build_day_select_required_windows,
    build_day_select_required_windows_post,
    compute_guaranteed_cbl,
    compute_guaranteed_event,
    compute_guaranteed_reward,
    build_guaranteed_required_windows,
    build_guaranteed_required_windows_post,
)

SAMPLES_DIR = Path(__file__).parent / "samples"


def _load_sample(name: str) -> Dict[str, Any]:
    with open(SAMPLES_DIR / name, "r") as f:
        return json.load(f)


def _build_or_error(build_fn):
    try:
        return build_fn()
    except HTTPException as e:
        return {"detail": e.detail}
    except Exception as e:
        return {"detail": f"示例產生失敗：{e}"}


# Request examples from samples
DAY_SELECT_CBL_REQUEST_EXAMPLE = _load_sample("day_select_batch_cbl_correct.json")
DAY_SELECT_REWARD_REQUEST_EXAMPLE = _load_sample("day_select_batch_reward_correct.json")
DAY_SELECT_REDUCTION_REQUEST_EXAMPLE = DAY_SELECT_REWARD_REQUEST_EXAMPLE
DAY_SELECT_CBL_REQUEST_ERROR = _load_sample("day_select_cbl_wrong.json")
DAY_SELECT_REWARD_REQUEST_ERROR = _load_sample("day_select_reward_wrong.json")
DAY_SELECT_REDUCTION_REQUEST_ERROR = DAY_SELECT_REWARD_REQUEST_ERROR

# Required windows requests derived from samples
DAY_SELECT_REQUIRED_REQUEST_EXAMPLE = {
    "customer_id": "C001",
    "event_start": DAY_SELECT_REWARD_REQUEST_EXAMPLE["event_start"],
    "event_end": DAY_SELECT_REWARD_REQUEST_EXAMPLE["event_end"],
    "batch_time_tariff": DAY_SELECT_REWARD_REQUEST_EXAMPLE.get("batch_time_tariff", False),
    "min_baseline_days": 20,
}
DAY_SELECT_REQUIRED_REQUEST_POST_EXAMPLE = {
    "customer_id": "C001",
    "event_start": DAY_SELECT_REWARD_REQUEST_EXAMPLE["event_start"],
    "event_end": DAY_SELECT_REWARD_REQUEST_EXAMPLE["event_end"],
    "batch_time_tariff": DAY_SELECT_REWARD_REQUEST_EXAMPLE.get("batch_time_tariff", False),
}

GUARANTEED_CBL_REQUEST_EXAMPLE = _load_sample("guaranteed_cbl_correct.json")
GUARANTEED_CBL_REQUEST_ERROR = _load_sample("guaranteed_cbl_wrong.json")
GUARANTEED_REWARD_REQUEST_EXAMPLE = _load_sample("guaranteed_reward_correct.json")
GUARANTEED_REWARD_REQUEST_ERROR = _load_sample("guaranteed_reward_wrong.json")
GUARANTEED_REQUIRED_REQUEST_EXAMPLE_PRE = {
    "customer_id": "G001",
    "event_start": GUARANTEED_REWARD_REQUEST_EXAMPLE["events"][0]["event_start"],
    "event_end": GUARANTEED_REWARD_REQUEST_EXAMPLE["events"][0]["event_end"],
    "notification_minutes_before": GUARANTEED_REWARD_REQUEST_EXAMPLE["notification_minutes_before"],
}
GUARANTEED_REQUIRED_REQUEST_EXAMPLE_POST = GUARANTEED_REQUIRED_REQUEST_EXAMPLE_PRE.copy()


def _build_day_select_cbl_response():
    req = DaySelectCBLRequest.model_validate(DAY_SELECT_CBL_REQUEST_EXAMPLE)
    resp = compute_day_select_cbl(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        batch_time_tariff=req.batch_time_tariff,
        assumed_af_kw=req.assumed_af_kw,
        contract_capacity_kw=req.contract_capacity_kw,
    )
    return resp.model_dump()


def _build_day_select_reward_response():
    req = DaySelectRewardRequest.model_validate(DAY_SELECT_REWARD_REQUEST_EXAMPLE)
    resp = compute_day_select_reward(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        batch_time_tariff=req.batch_time_tariff,
        assumed_af_kw=req.assumed_af_kw,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
    )
    return resp.model_dump()


def _build_day_select_reduction_response():
    req = DaySelectReductionRequest.model_validate(DAY_SELECT_REDUCTION_REQUEST_EXAMPLE)
    resp = compute_day_select_reduction(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        batch_time_tariff=req.batch_time_tariff,
        assumed_af_kw=req.assumed_af_kw,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
    )
    return resp.model_dump()


def _build_day_select_cbl_error():
    req = DaySelectCBLRequest.model_validate(DAY_SELECT_CBL_REQUEST_ERROR)
    compute_day_select_cbl(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        batch_time_tariff=req.batch_time_tariff,
        assumed_af_kw=req.assumed_af_kw,
        contract_capacity_kw=req.contract_capacity_kw,
    )
    raise RuntimeError("預期錯誤示例，但計算成功")


def _build_day_select_reward_error():
    req = DaySelectRewardRequest.model_validate(DAY_SELECT_REWARD_REQUEST_ERROR)
    compute_day_select_reward(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        batch_time_tariff=req.batch_time_tariff,
        assumed_af_kw=req.assumed_af_kw,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
    )
    raise RuntimeError("預期錯誤示例，但計算成功")


def _build_day_select_reduction_error():
    req = DaySelectReductionRequest.model_validate(DAY_SELECT_REDUCTION_REQUEST_ERROR)
    compute_day_select_reduction(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        batch_time_tariff=req.batch_time_tariff,
        assumed_af_kw=req.assumed_af_kw,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
    )
    raise RuntimeError("預期錯誤示例，但計算成功")


# Guaranteed helpers
def _build_guaranteed_cbl_response():
    req = GuaranteedCBLRequest.model_validate(GUARANTEED_CBL_REQUEST_EXAMPLE)
    resp = compute_guaranteed_cbl(
        customer_id=req.customer_id,
        event_start=req.event_start,
        records=req.records,
        notification_minutes_before=req.notification_minutes_before,
        contract_capacity_kw=req.contract_capacity_kw,
    )
    return resp.model_dump()


def _build_guaranteed_event_request_from_reward(data: Dict[str, Any]) -> Dict[str, Any]:
    event = data["events"][0]
    return {
        "customer_id": data["customer_id"],
        "event_start": event["event_start"],
        "event_end": event["event_end"],
        "records": data["records"],
        "notification_minutes_before": data["notification_minutes_before"],
        "contract_capacity_kw": data["contract_capacity_kw"],
        "committed_capacity_kw": data.get("committed_capacity_kw"),
        "basic_fee_rate": data.get("basic_fee_rate"),
        "flow_fee_rate": data.get("flow_fee_rate"),
    }


GUARANTEED_EVENT_REQUEST_EXAMPLE = _build_guaranteed_event_request_from_reward(GUARANTEED_REWARD_REQUEST_EXAMPLE)
GUARANTEED_EVENT_REQUEST_ERROR = _build_guaranteed_event_request_from_reward(GUARANTEED_REWARD_REQUEST_ERROR)


def _build_guaranteed_event_response():
    req = GuaranteedEventRequest.model_validate(GUARANTEED_EVENT_REQUEST_EXAMPLE)
    resp = compute_guaranteed_event(
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
    return resp.model_dump()


def _build_guaranteed_reward_response():
    req = GuaranteedRewardRequest.model_validate(GUARANTEED_REWARD_REQUEST_EXAMPLE)
    resp = compute_guaranteed_reward(
        customer_id=req.customer_id,
        notification_minutes_before=req.notification_minutes_before,
        contract_capacity_kw=req.contract_capacity_kw,
        events=req.events,
        records=req.records,
        committed_capacity_kw=req.committed_capacity_kw,
        basic_fee_rate=req.basic_fee_rate,
        flow_fee_rate=req.flow_fee_rate,
    )
    return resp.model_dump()


def _build_guaranteed_cbl_error():
    req = GuaranteedCBLRequest.model_validate(GUARANTEED_CBL_REQUEST_ERROR)
    compute_guaranteed_cbl(
        customer_id=req.customer_id,
        event_start=req.event_start,
        records=req.records,
        notification_minutes_before=req.notification_minutes_before,
        contract_capacity_kw=req.contract_capacity_kw,
    )
    raise RuntimeError("預期錯誤示例，但計算成功")


def _build_guaranteed_event_error():
    req = GuaranteedEventRequest.model_validate(GUARANTEED_EVENT_REQUEST_ERROR)
    compute_guaranteed_event(
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
    raise RuntimeError("預期錯誤示例，但計算成功")


def _build_guaranteed_reward_error():
    req = GuaranteedRewardRequest.model_validate(GUARANTEED_REWARD_REQUEST_ERROR)
    compute_guaranteed_reward(
        customer_id=req.customer_id,
        notification_minutes_before=req.notification_minutes_before,
        contract_capacity_kw=req.contract_capacity_kw,
        events=req.events,
        records=req.records,
        committed_capacity_kw=req.committed_capacity_kw,
        basic_fee_rate=req.basic_fee_rate,
        flow_fee_rate=req.flow_fee_rate,
    )
    raise RuntimeError("預期錯誤示例，但計算成功")


def _build_day_select_required_response():
    req = DaySelectRequiredRequest.model_validate(DAY_SELECT_REQUIRED_REQUEST_EXAMPLE)
    resp = build_day_select_required_windows(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        batch_time_tariff=req.batch_time_tariff,
        min_baseline_days=req.min_baseline_days,
    )
    return resp.model_dump()


def _build_day_select_required_post_response():
    req = DaySelectRequiredRequest.model_validate(DAY_SELECT_REQUIRED_REQUEST_POST_EXAMPLE)
    resp = build_day_select_required_windows_post(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        batch_time_tariff=req.batch_time_tariff,
    )
    return resp.model_dump()


def _build_guaranteed_required_response():
    req = GuaranteedRequiredRequest.model_validate(GUARANTEED_REQUIRED_REQUEST_EXAMPLE_PRE)
    resp = build_guaranteed_required_windows(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        notification_minutes_before=req.notification_minutes_before,
    )
    return resp.model_dump()


def _build_guaranteed_required_post_response():
    req = GuaranteedRequiredRequest.model_validate(GUARANTEED_REQUIRED_REQUEST_EXAMPLE_POST)
    resp = build_guaranteed_required_windows_post(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        notification_minutes_before=req.notification_minutes_before,
    )
    return resp.model_dump()


DAY_SELECT_CBL_RESPONSE_EXAMPLE = _build_or_error(_build_day_select_cbl_response)
DAY_SELECT_REWARD_RESPONSE_EXAMPLE = _build_or_error(_build_day_select_reward_response)
DAY_SELECT_REDUCTION_RESPONSE_EXAMPLE = _build_or_error(_build_day_select_reduction_response)
DAY_SELECT_CBL_ERROR_EXAMPLE = _build_or_error(_build_day_select_cbl_error)
DAY_SELECT_REWARD_ERROR_EXAMPLE = _build_or_error(_build_day_select_reward_error)
DAY_SELECT_REDUCTION_ERROR_EXAMPLE = _build_or_error(_build_day_select_reduction_error)

GUARANTEED_CBL_RESPONSE_EXAMPLE = _build_or_error(_build_guaranteed_cbl_response)
GUARANTEED_EVENT_RESPONSE_EXAMPLE = _build_or_error(_build_guaranteed_event_response)
GUARANTEED_REWARD_RESPONSE_EXAMPLE = _build_or_error(_build_guaranteed_reward_response)
GUARANTEED_CBL_ERROR_EXAMPLE = _build_or_error(_build_guaranteed_cbl_error)
GUARANTEED_EVENT_ERROR_EXAMPLE = _build_or_error(_build_guaranteed_event_error)
GUARANTEED_REWARD_ERROR_EXAMPLE = _build_or_error(_build_guaranteed_reward_error)
DAY_SELECT_REQUIRED_RESPONSE_EXAMPLE = _build_or_error(_build_day_select_required_response)
DAY_SELECT_REQUIRED_POST_RESPONSE_EXAMPLE = _build_or_error(_build_day_select_required_post_response)
GUARANTEED_REQUIRED_RESPONSE_EXAMPLE = _build_or_error(_build_guaranteed_required_response)
GUARANTEED_REQUIRED_POST_RESPONSE_EXAMPLE = _build_or_error(_build_guaranteed_required_post_response)
