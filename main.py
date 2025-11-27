from fastapi import FastAPI, Body

from schemas import (
    DaySelectCBLRequest,
    DaySelectCBLResponse,
    DaySelectReductionRequest,
    DaySelectRewardResponse,
    DaySelectRewardRequest,
    DaySelectRewardResponse,
    DaySelectMonthlySettlementRequest,
    DaySelectMonthlySettlementResponse,
    DaySelectRequiredRequest,
    DaySelectRequiredPreResponse,
    DaySelectRequiredPostResponse,
    DaySelectSettlementRequiredRequest,
    GuaranteedCBLRequest,
    GuaranteedCBLResponse,
    GuaranteedEventRequest,
    GuaranteedEventResponse,
    GuaranteedRewardRequest,
    GuaranteedRewardResponse,
    GuaranteedRequiredRequest,
    GuaranteedRequiredPreResponse,
    GuaranteedRequiredPostResponse,
)
from services import (
    compute_day_select_cbl,
    compute_day_select_reduction,
    compute_day_select_reward,
    compute_day_select_settlement_monthly,
    build_day_select_settlement_required,
    build_day_select_required_windows,
    build_day_select_required_windows_post,
    compute_guaranteed_cbl,
    compute_guaranteed_event,
    compute_guaranteed_reward,
    build_guaranteed_required_windows,
    build_guaranteed_required_windows_post,
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
    DAY_SELECT_SETTLEMENT_MONTHLY_REQUEST_EXAMPLE,
    DAY_SELECT_SETTLEMENT_MONTHLY_RESPONSE_EXAMPLE,
    DAY_SELECT_REQUIRED_RESPONSE_EXAMPLE,
    DAY_SELECT_REQUIRED_REQUEST_EXAMPLE,
    DAY_SELECT_REQUIRED_POST_RESPONSE_EXAMPLE,
    GUARANTEED_CBL_ERROR_EXAMPLE,
    GUARANTEED_CBL_RESPONSE_EXAMPLE,
    GUARANTEED_CBL_REQUEST_EXAMPLE,
    GUARANTEED_EVENT_ERROR_EXAMPLE,
    GUARANTEED_EVENT_RESPONSE_EXAMPLE,
    GUARANTEED_EVENT_REQUEST_EXAMPLE,
    GUARANTEED_REWARD_ERROR_EXAMPLE,
    GUARANTEED_REWARD_RESPONSE_EXAMPLE,
    GUARANTEED_REWARD_REQUEST_EXAMPLE,
    GUARANTEED_REQUIRED_RESPONSE_EXAMPLE,
    GUARANTEED_REQUIRED_POST_RESPONSE_EXAMPLE,
    GUARANTEED_REQUIRED_REQUEST_EXAMPLE_PRE,
    GUARANTEED_REQUIRED_REQUEST_EXAMPLE_POST,
)

app = FastAPI(
    title="Taipower DR API Server",
    version="1.1.0",
    description=(
        "Taipower DR API：日選（時段型）與保證反應型的 CBL、實際抑低與回饋金計算。\n"
        "日選：/dr/day-select/cbl、/reward、/reduction，以及對應的需求視窗查詢 (cbl/reward/reduction)。\n"
        "保證：/dr/guaranteed/cbl、/reduction、/reward，以及對應的需求視窗查詢 (cbl/reward/reduction)。\n"
        "需求視窗端點會回傳需要的 15 分鐘資料區間，方便在事件前後蒐集或檢核資料。"
    ),
)


@app.post(
    "/dr/day-select/cbl/required-records",
    response_model=DaySelectRequiredPreResponse,
    tags=["Day-Select: CBL"],
    responses={
        200: {"description": "取得需求日列表（事件前，用於 CBL 計算；整日資料，含 20 基準日＋事件日）", "content": {"application/json": {"example": DAY_SELECT_REQUIRED_RESPONSE_EXAMPLE}}},
    },
)
def api_day_select_required_records_pre(req: DaySelectRequiredRequest = Body(..., examples={"default": DAY_SELECT_REQUIRED_REQUEST_EXAMPLE})):
    return build_day_select_required_windows(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        batch_time_tariff=req.batch_time_tariff,
        min_baseline_days=req.min_baseline_days,
        dr_periods=req.dr_periods,
    )



@app.post(
    "/dr/day-select/settlement/required-records",
    response_model=DaySelectRequiredPostResponse,
    tags=["Day-Select: Settlement"],
    responses={
        200: {"description": "取得需求日列表（事件後，用於月度 settlement；整日資料，含 20 基準日＋所有事件日）", "content": {"application/json": {"example": DAY_SELECT_REQUIRED_POST_RESPONSE_EXAMPLE}}},
    },
)
def api_day_select_required_records_settlement(req: DaySelectSettlementRequiredRequest):
    return build_day_select_settlement_required(
        customer_id=req.customer_id,
        events=req.events,
        dr_periods=req.dr_periods,
        min_baseline_days=req.min_baseline_days,
    )



@app.post(
    "/dr/day-select/reduction/required-records",
    response_model=DaySelectRequiredPostResponse,
    tags=["Day-Select: Reduction"],
    responses={
        200: {"description": "取得需求日列表（事件後，用於 reduction；整日資料，含 20 基準日＋事件日）", "content": {"application/json": {"example": DAY_SELECT_REQUIRED_POST_RESPONSE_EXAMPLE}}},
    },
)
def api_day_select_required_records_reduction(req: DaySelectRequiredRequest = Body(..., examples={"default": DAY_SELECT_REQUIRED_REQUEST_EXAMPLE})):
    return build_day_select_required_windows_post(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        batch_time_tariff=req.batch_time_tariff,
        dr_periods=req.dr_periods,
        min_baseline_days=req.min_baseline_days,
    )



@app.post(
    "/dr/day-select/cbl",
    response_model=DaySelectCBLResponse,
    description="計算日選方案基準用電 (CBL)，含 CBL1+AF 並套用契約容量上限；需 15 分鐘紀錄、基準日/事件日 22:00-24:00 視窗。建議先呼叫 /dr/day-select/cbl/required-records 取得需求時間窗，再送出此計算。",
    tags=["Day-Select: CBL"],
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": DAY_SELECT_CBL_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤", "content": {"application/json": {"example": DAY_SELECT_CBL_ERROR_EXAMPLE}}},
    },
)
def api_day_select_cbl(req: DaySelectCBLRequest = Body(..., examples={"default": DAY_SELECT_CBL_REQUEST_EXAMPLE})):
    return compute_day_select_cbl(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        batch_time_tariff=req.batch_time_tariff,
        assumed_af_kw=req.assumed_af_kw,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
        dr_periods=req.dr_periods,
    )


@app.post(
    "/dr/day-select/settlement",
    response_model=DaySelectMonthlySettlementResponse,
    description="日選方案月度結算：多事件回饋金加總，逐事件依 2/4/6 小時費率計算。建議先呼叫 /dr/day-select/settlement/required-records 取得需求時間窗，確保資料齊全。",
    tags=["Day-Select: Settlement"],
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": DAY_SELECT_SETTLEMENT_MONTHLY_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤"},
    },
)
def api_day_select_settlement(req: DaySelectMonthlySettlementRequest = Body(..., examples={"default": DAY_SELECT_SETTLEMENT_MONTHLY_REQUEST_EXAMPLE})):
    return compute_day_select_settlement_monthly(
        customer_id=req.customer_id,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
        dr_periods=req.dr_periods,
        records=req.records,
        events=req.events,
    )


@app.post(
    "/dr/day-select/reduction",
    response_model=DaySelectRewardResponse,
    description="計算日選方案單次抑低並計算回饋金（含 CBL/AF、執行率/減載比率與費率）。建議先呼叫 /dr/day-select/reduction/required-records 取得需求日列表，確保資料齊全。",
    tags=["Day-Select: Reduction"],
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": DAY_SELECT_REWARD_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤", "content": {"application/json": {"example": DAY_SELECT_REWARD_ERROR_EXAMPLE}}},
    },
)
def api_day_select_reduction(req: DaySelectReductionRequest = Body(..., examples={"default": DAY_SELECT_REDUCTION_REQUEST_EXAMPLE})):
    return compute_day_select_reduction(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        batch_time_tariff=req.batch_time_tariff,
        assumed_af_kw=req.assumed_af_kw,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
        dr_periods=req.dr_periods,
    )


@app.post(
    "/dr/guaranteed/cbl/required-records",
    response_model=GuaranteedRequiredPreResponse,
    tags=["Guaranteed: CBL"],
    responses={
        200: {"description": "取得需求時間窗（事件前，用於 CBL 計算）", "content": {"application/json": {"example": GUARANTEED_REQUIRED_RESPONSE_EXAMPLE}}},
    },
)
def api_guaranteed_required_records_pre(req: GuaranteedRequiredRequest = Body(..., examples={"default": GUARANTEED_REQUIRED_REQUEST_EXAMPLE_PRE})):
    return build_guaranteed_required_windows(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        notification_minutes_before=req.notification_minutes_before,
        dr_periods=req.dr_periods,
    )



@app.post(
    "/dr/guaranteed/reward/required-records",
    response_model=GuaranteedRequiredPostResponse,
    tags=["Guaranteed: Settlement"],
    responses={
        200: {"description": "取得需求時間窗（事件後，用於 reward/reduction）", "content": {"application/json": {"example": GUARANTEED_REQUIRED_POST_RESPONSE_EXAMPLE}}},
    },
)
def api_guaranteed_required_records_reward(req: GuaranteedRequiredRequest = Body(..., examples={"default": GUARANTEED_REQUIRED_REQUEST_EXAMPLE_POST})):
    return build_guaranteed_required_windows_post(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        notification_minutes_before=req.notification_minutes_before,
        dr_periods=req.dr_periods,
    )



@app.post(
    "/dr/guaranteed/reduction/required-records",
    response_model=GuaranteedRequiredPostResponse,
    tags=["Guaranteed: Reduction"],
    responses={
        200: {"description": "取得需求時間窗（事件後，用於 reward/reduction）", "content": {"application/json": {"example": GUARANTEED_REQUIRED_POST_RESPONSE_EXAMPLE}}},
    },
)
def api_guaranteed_required_records_reduction(req: GuaranteedRequiredRequest = Body(..., examples={"default": GUARANTEED_REQUIRED_REQUEST_EXAMPLE_POST})):
    return build_guaranteed_required_windows_post(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        notification_minutes_before=req.notification_minutes_before,
        dr_periods=req.dr_periods,
    )

@app.post(
    "/dr/guaranteed/cbl",
    response_model=GuaranteedCBLResponse,
    description="依保證反應型規範與通知提前時間計算事件基準需量 (CBL)。建議先呼叫 /dr/guaranteed/cbl/required-records 取得需求時間窗，確保資料齊全。",
    tags=["Guaranteed: CBL"],
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": GUARANTEED_CBL_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤", "content": {"application/json": {"example": GUARANTEED_CBL_ERROR_EXAMPLE}}},
    },
)
def api_guaranteed_cbl(req: GuaranteedCBLRequest = Body(..., examples={"default": GUARANTEED_CBL_REQUEST_EXAMPLE})):
    return compute_guaranteed_cbl(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        notification_minutes_before=req.notification_minutes_before,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
        dr_periods=req.dr_periods,
    )


@app.post(
    "/dr/guaranteed/reduction",
    response_model=GuaranteedEventResponse,
    description="計算保證反應型單次事件的基準需量、實際抑低容量與執行率（不計算基本電費與流動電費扣減/違約）。建議先呼叫 /dr/guaranteed/reduction/required-records 取得需求時間窗。",
    tags=["Guaranteed: Reduction"],
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": GUARANTEED_EVENT_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤", "content": {"application/json": {"example": GUARANTEED_EVENT_ERROR_EXAMPLE}}},
    },
)
def api_guaranteed_reduction(req: GuaranteedEventRequest = Body(..., examples={"default": GUARANTEED_EVENT_REQUEST_EXAMPLE})):
    return compute_guaranteed_reduction_simple(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        notification_minutes_before=req.notification_minutes_before,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
        records=req.records,
        dr_periods=req.dr_periods,
    )


@app.post(
    "/dr/guaranteed/settlement",
    response_model=GuaranteedRewardResponse,
    description="彙總本月所有保證反應型事件，計算基本電費與流動電費扣減、違約金與淨回饋（**月度結算**）。建議先呼叫 /dr/guaranteed/reward/required-records 取得需求時間窗。",
    tags=["Guaranteed: Settlement"],
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": GUARANTEED_REWARD_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤", "content": {"application/json": {"example": GUARANTEED_REWARD_ERROR_EXAMPLE}}},
    },
)
def api_guaranteed_reward(req: GuaranteedRewardRequest = Body(..., examples={"default": GUARANTEED_REWARD_REQUEST_EXAMPLE})):
    return compute_guaranteed_reward(
        customer_id=req.customer_id,
        notification_minutes_before=req.notification_minutes_before,
        contract_capacity_kw=req.contract_capacity_kw,
        committed_capacity_kw=req.committed_capacity_kw,
        events=req.events,
        records=req.records,
        basic_fee_rate=req.basic_fee_rate,
        flow_fee_rate=req.flow_fee_rate,
        dr_periods=req.dr_periods,
    )
