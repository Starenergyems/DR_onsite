from fastapi import FastAPI, Body

from schemas import (
    DaySelectCBLRequest,
    DaySelectCBLResponse,
    DaySelectReductionRequest,
    DaySelectReductionResponse,
    DaySelectRewardRequest,
    DaySelectRewardResponse,
    GuaranteedCBLRequest,
    GuaranteedCBLResponse,
    GuaranteedEventRequest,
    GuaranteedEventResponse,
    GuaranteedRewardRequest,
    GuaranteedRewardResponse,
)
from services import (
    compute_day_select_cbl,
    compute_day_select_reduction,
    compute_day_select_reward,
    compute_guaranteed_cbl,
    compute_guaranteed_event,
    compute_guaranteed_reward,
)
from swagger_examples import (
    DAY_SELECT_CBL_ERROR_EXAMPLE,
    DAY_SELECT_CBL_RESPONSE_EXAMPLE,
    DAY_SELECT_CBL_REQUEST_EXAMPLE,
    DAY_SELECT_REDUCTION_ERROR_EXAMPLE,
    DAY_SELECT_REDUCTION_RESPONSE_EXAMPLE,
    DAY_SELECT_REDUCTION_REQUEST_EXAMPLE,
    DAY_SELECT_REWARD_ERROR_EXAMPLE,
    DAY_SELECT_REWARD_RESPONSE_EXAMPLE,
    DAY_SELECT_REWARD_REQUEST_EXAMPLE,
    GUARANTEED_CBL_ERROR_EXAMPLE,
    GUARANTEED_CBL_RESPONSE_EXAMPLE,
    GUARANTEED_CBL_REQUEST_EXAMPLE,
    GUARANTEED_EVENT_ERROR_EXAMPLE,
    GUARANTEED_EVENT_RESPONSE_EXAMPLE,
    GUARANTEED_EVENT_REQUEST_EXAMPLE,
    GUARANTEED_REWARD_ERROR_EXAMPLE,
    GUARANTEED_REWARD_RESPONSE_EXAMPLE,
    GUARANTEED_REWARD_REQUEST_EXAMPLE,
)

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


@app.post(
    "/dr/day-select/cbl",
    response_model=DaySelectCBLResponse,
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": DAY_SELECT_CBL_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤", "content": {"application/json": {"example": DAY_SELECT_CBL_ERROR_EXAMPLE}}},
    },
)
def api_day_select_cbl(req: DaySelectCBLRequest = Body(..., example=DAY_SELECT_CBL_REQUEST_EXAMPLE)):
    return compute_day_select_cbl(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        batch_time_tariff=req.batch_time_tariff,
        assumed_today_adjust_avg_kw=req.assumed_adjust_avg_kw,
        contract_capacity_kw=req.contract_capacity_kw,
    )


@app.post(
    "/dr/day-select/reward",
    response_model=DaySelectRewardResponse,
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": DAY_SELECT_REWARD_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤", "content": {"application/json": {"example": DAY_SELECT_REWARD_ERROR_EXAMPLE}}},
    },
)
def api_day_select_reward(req: DaySelectRewardRequest = Body(..., example=DAY_SELECT_REWARD_REQUEST_EXAMPLE)):
    return compute_day_select_reward(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        batch_time_tariff=req.batch_time_tariff,
        assumed_today_adjust_avg_kw=req.assumed_adjust_avg_kw,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
    )


@app.post(
    "/dr/day-select/reduction",
    response_model=DaySelectReductionResponse,
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": DAY_SELECT_REDUCTION_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤", "content": {"application/json": {"example": DAY_SELECT_REDUCTION_ERROR_EXAMPLE}}},
    },
)
def api_day_select_reduction(req: DaySelectReductionRequest = Body(..., example=DAY_SELECT_REDUCTION_REQUEST_EXAMPLE)):
    return compute_day_select_reduction(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        batch_time_tariff=req.batch_time_tariff,
        assumed_today_adjust_avg_kw=req.assumed_adjust_avg_kw,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
    )


@app.post(
    "/dr/guaranteed/cbl",
    response_model=GuaranteedCBLResponse,
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": GUARANTEED_CBL_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤", "content": {"application/json": {"example": GUARANTEED_CBL_ERROR_EXAMPLE}}},
    },
)
def api_guaranteed_cbl(req: GuaranteedCBLRequest = Body(..., example=GUARANTEED_CBL_REQUEST_EXAMPLE)):
    return compute_guaranteed_cbl(
        customer_id=req.customer_id,
        event_start=req.event_start,
        records=req.records,
        notification_minutes_before=req.notification_minutes_before,
        contract_capacity_kw=req.contract_capacity_kw,
    )


@app.post(
    "/dr/guaranteed/reduction",
    response_model=GuaranteedEventResponse,
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": GUARANTEED_EVENT_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤", "content": {"application/json": {"example": GUARANTEED_EVENT_ERROR_EXAMPLE}}},
    },
)
def api_guaranteed_reduction(req: GuaranteedEventRequest = Body(..., example=GUARANTEED_EVENT_REQUEST_EXAMPLE)):
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


@app.post(
    "/dr/guaranteed/reward",
    response_model=GuaranteedRewardResponse,
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": GUARANTEED_REWARD_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤", "content": {"application/json": {"example": GUARANTEED_REWARD_ERROR_EXAMPLE}}},
    },
)
def api_guaranteed_reward(req: GuaranteedRewardRequest = Body(..., example=GUARANTEED_REWARD_REQUEST_EXAMPLE)):
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
