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
    GuaranteedSettlementRequiredRequest,
    SpinReserveCBLRequest,
    SpinReserveCBLResponse,
    SpinReserveRequiredRequest,
    SpinReserveRequiredResponse,
    SpinReserveReductionRequiredRequest,
    SpinReserveReductionRequiredResponse,
    SpinReserveReductionRequest,
    SpinReserveReductionResponse,
    SpinReserveSettlementRequiredRequest,
    SpinReserveSettlementRequiredResponse,
    SpinReserveSettlementRequest,
    SpinReserveSettlementResponse,
    SampleDaySelectRequest,
    SampleGuaranteedRequest,
    SampleSpinReserveRequest,
    SampleRecordsResponse,
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
    compute_guaranteed_reduction_simple,
    compute_guaranteed_reward,
    build_guaranteed_required_windows,
    build_guaranteed_required_windows_post,
    build_guaranteed_settlement_required,
    compute_spin_reserve_cbl,
    build_spin_reserve_required_windows,
    build_spin_reserve_reduction_required_windows,
    build_spin_reserve_settlement_required,
    compute_spin_reserve_reduction,
    compute_spin_reserve_settlement,
    generate_day_select_samples,
    generate_guaranteed_samples,
    generate_spin_reserve_samples,
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
    GUARANTEED_SETTLEMENT_REQUIRED_RESPONSE_EXAMPLE,
    GUARANTEED_REQUIRED_RESPONSE_EXAMPLE,
    GUARANTEED_REQUIRED_POST_RESPONSE_EXAMPLE,
    GUARANTEED_REQUIRED_REQUEST_EXAMPLE_PRE,
    GUARANTEED_REQUIRED_REQUEST_EXAMPLE_POST,
    SPIN_RESERVE_CBL_RESPONSE_EXAMPLE,
    SPIN_RESERVE_CBL_REQUEST_EXAMPLE,
    SPIN_RESERVE_REQUIRED_REQUEST_EXAMPLE,
    SPIN_RESERVE_REQUIRED_RESPONSE_EXAMPLE,
    SPIN_RESERVE_REDUCTION_REQUIRED_RESPONSE_EXAMPLE,
    SPIN_RESERVE_REDUCTION_REQUEST_EXAMPLE,
    SPIN_RESERVE_REDUCTION_RESPONSE_EXAMPLE,
    SPIN_RESERVE_REDUCTION_REQUIRED_REQUEST_EXAMPLE,
    SPIN_RESERVE_SETTLEMENT_REQUIRED_RESPONSE_EXAMPLE,
    SPIN_RESERVE_SETTLEMENT_REQUIRED_REQUEST_EXAMPLE,
    SPIN_RESERVE_SETTLEMENT_REQUEST_EXAMPLE,
    SPIN_RESERVE_SETTLEMENT_RESPONSE_EXAMPLE,
)

app = FastAPI(
    title="Taipower DR API Server",
    version="1.1.0",
    description=(
        "Taipower DR API：日選（時段型）與保證反應型的 CBL、實際抑低與回饋金計算。\n"
        "日選：/dr/day-select/cbl、/reward、/reduction，以及對應的需求視窗查詢 (cbl/reward/reduction)。\n"
        "保證：/dr/guaranteed/cbl、/reduction、/reward，以及對應的需求視窗查詢 (cbl/reward/reduction)。\n"
        "即時備轉：/dr/spin-reserve/cbl/required-records、/dr/spin-reserve/cbl，依調度前 5 分鐘平均功率計算 CBL（事件日即為抑低日，僅需前 5 分鐘基準資料）。\n"
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
        200: {"description": "取得需求日列表（事件前，用於 CBL 計算；整日資料，事件日）", "content": {"application/json": {"example": GUARANTEED_REQUIRED_RESPONSE_EXAMPLE}}},
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
        200: {"description": "取得需求日列表（事件後，用於 reward/reduction；整日資料，事件日）", "content": {"application/json": {"example": GUARANTEED_REQUIRED_POST_RESPONSE_EXAMPLE}}},
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
        200: {"description": "取得需求日列表（事件後，用於 reward/reduction；整日資料，事件日）", "content": {"application/json": {"example": GUARANTEED_REQUIRED_POST_RESPONSE_EXAMPLE}}},
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
    "/dr/guaranteed/settlement/required-records",
    response_model=GuaranteedRequiredPostResponse,
    tags=["Guaranteed: Settlement"],
    responses={
        200: {"description": "取得需求日列表（事件後，用於月度 settlement；整日資料，事件日）", "content": {"application/json": {"example": GUARANTEED_SETTLEMENT_REQUIRED_RESPONSE_EXAMPLE}}},
    },
)
def api_guaranteed_required_records_settlement(req: GuaranteedSettlementRequiredRequest):
    return build_guaranteed_settlement_required(
        customer_id=req.customer_id,
        events=req.events,
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
    description="計算保證反應型單次事件的基準需量、實際抑低容量、執行率與流動電費獎懲。建議先呼叫 /dr/guaranteed/reduction/required-records 取得需求日列表，送入整日 15 分鐘資料。",
    tags=["Guaranteed: Reduction"],
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": GUARANTEED_EVENT_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤", "content": {"application/json": {"example": GUARANTEED_EVENT_ERROR_EXAMPLE}}},
    },
)
def api_guaranteed_reduction(req: GuaranteedEventRequest = Body(..., examples={"default": GUARANTEED_EVENT_REQUEST_EXAMPLE})):
    return compute_guaranteed_event(
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
        prior_basic_reduction_amounts=req.prior_basic_reduction_amounts,
        dr_periods=req.dr_periods,
    )


@app.post(
    "/dr/spin-reserve/cbl/required-records",
    response_model=SpinReserveRequiredResponse,
    tags=["Spin Reserve: CBL"],
    responses={
        200: {
            "description": "取得需求時間窗（事件前，用於即時備轉 CBL 計算；5 分鐘平均）",
            "content": {"application/json": {"example": SPIN_RESERVE_REQUIRED_RESPONSE_EXAMPLE}},
        },
    },
)
def api_spin_reserve_required_records(req: SpinReserveRequiredRequest = Body(..., examples={"default": SPIN_RESERVE_REQUIRED_REQUEST_EXAMPLE})):
    return build_spin_reserve_required_windows(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
    )


@app.post(
    "/dr/spin-reserve/cbl",
    response_model=SpinReserveCBLResponse,
    description="依需量反應即時備轉規範：調度指令下達時間點往前 5 分鐘平均功率為 CBL，並可套用約定抑低契約容量計算目標負載。",
    tags=["Spin Reserve: CBL"],
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": SPIN_RESERVE_CBL_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤"},
    },
)
def api_spin_reserve_cbl(req: SpinReserveCBLRequest = Body(..., examples={"default": SPIN_RESERVE_CBL_REQUEST_EXAMPLE})):
    return compute_spin_reserve_cbl(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        bid_capacity_kw=req.bid_capacity_kw,
        awarded_capacity_kw=req.awarded_capacity_kw,
    )


@app.post(
    "/dr/spin-reserve/reduction/required-records",
    response_model=SpinReserveReductionRequiredResponse,
    tags=["Spin Reserve: Reduction"],
    responses={
        200: {
            "description": "取得需求時間窗（事件後，用於即時備轉抑低與結算；含調度前 5 分鐘與事件時段）",
            "content": {"application/json": {"example": SPIN_RESERVE_REDUCTION_REQUIRED_RESPONSE_EXAMPLE}},
        },
    },
)
def api_spin_reserve_reduction_required_records(req: SpinReserveReductionRequiredRequest = Body(..., examples={"default": SPIN_RESERVE_REDUCTION_REQUIRED_REQUEST_EXAMPLE})):
    return build_spin_reserve_reduction_required_windows(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
    )


@app.post(
    "/dr/spin-reserve/reduction",
    response_model=SpinReserveReductionResponse,
    description="計算即時備轉單次事件的基準需量、實際抑低、執行率/服務品質與日結算金。建議先呼叫 /reduction/required-records 取得需求時間窗。",
    tags=["Spin Reserve: Reduction"],
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": SPIN_RESERVE_REDUCTION_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤"},
    },
)
def api_spin_reserve_reduction(req: SpinReserveReductionRequest = Body(..., examples={"default": SPIN_RESERVE_REDUCTION_REQUEST_EXAMPLE})):
    return compute_spin_reserve_reduction(
        customer_id=req.customer_id,
        event_start=req.event_start,
        event_end=req.event_end,
        records=req.records,
        awarded_capacity_kw=req.awarded_capacity_kw,
        efficiency_level=req.efficiency_level,
        is_dispatched=req.is_dispatched,
        capacity_price_per_kw=req.capacity_price_per_kw,
        energy_price_per_kwh=req.energy_price_per_kwh,
    )


@app.post(
    "/dr/spin-reserve/settlement/required-records",
    response_model=SpinReserveSettlementRequiredResponse,
    tags=["Spin Reserve: Settlement"],
    responses={
        200: {
            "description": "取得需求時間窗（事件後，用於月度結算；含各得標日調度前 5 分鐘與事件時段）",
            "content": {"application/json": {"example": SPIN_RESERVE_SETTLEMENT_REQUIRED_RESPONSE_EXAMPLE}},
        },
    },
)
def api_spin_reserve_settlement_required_records(req: SpinReserveSettlementRequiredRequest = Body(..., examples={"default": SPIN_RESERVE_SETTLEMENT_REQUIRED_REQUEST_EXAMPLE})):
    return build_spin_reserve_settlement_required(
        customer_id=req.customer_id,
        events=req.events,
    )


@app.post(
    "/dr/spin-reserve/settlement",
    response_model=SpinReserveSettlementResponse,
    description="即時備轉月度結算：累計多事件的日結算金，包含容量費、效能費（乘服務品質指標）、電能費總和。",
    tags=["Spin Reserve: Settlement"],
    responses={
        200: {"description": "計算成功", "content": {"application/json": {"example": SPIN_RESERVE_SETTLEMENT_RESPONSE_EXAMPLE}}},
        400: {"description": "請求錯誤"},
    },
)
def api_spin_reserve_settlement(req: SpinReserveSettlementRequest = Body(..., examples={"default": SPIN_RESERVE_SETTLEMENT_REQUEST_EXAMPLE})):
    return compute_spin_reserve_settlement(
        customer_id=req.customer_id,
        events=req.events,
        records=req.records,
    )


# -------------------------
# Samples endpoints
# -------------------------
@app.post(
    "/dr/day-select/sample-records",
    response_model=SampleRecordsResponse,
    tags=["Samples"],
    summary="產生日選型 15 分鐘模擬資料",
)
def api_sample_day_select_records(
    req: SampleDaySelectRequest = Body(
        ..., 
        examples={
            "default": {
                "customer_id": "C001",
                "sample_date": "2099-01-02",
                "event_start": "16:00:00",
                "event_end": "20:00:00",
                "base_kw": 1500,
                "event_kw": 500,
                "af_kw": 0,
                "batch_time_tariff": False,
                "dr_periods": [{"start": "2099-01", "end": "2099-12"}],
                "contract_capacity_kw": 120,
                "committed_capacity_kw": 80,
                "baseline_days": 5,
                "assumed_af_kw": 0,
            }
        },
    )
):
    return generate_day_select_samples(req)


@app.post(
    "/dr/guaranteed/sample-records",
    response_model=SampleRecordsResponse,
    tags=["Samples"],
    summary="產生保證型 15 分鐘模擬資料",
)
def api_sample_guaranteed_records(
    req: SampleGuaranteedRequest = Body(
        ...,
        examples={
            "default": {
                "customer_id": "G001",
                "sample_date": "2099-01-10",
                "event_start": "16:00:00",
                "event_end": "18:00:00",
                "base_kw": 1500,
                "event_kw": 500,
                "notification_minutes_before": 60,
                "contract_capacity_kw": 2000,
                "committed_capacity_kw": 1200,
            }
        },
    )
):
    return generate_guaranteed_samples(req)


@app.post(
    "/dr/spin-reserve/sample-records",
    response_model=SampleRecordsResponse,
    tags=["Samples"],
    summary="產生即時備轉 1 分鐘模擬資料（含前後緩衝）",
)
def api_sample_spin_reserve_records(
    req: SampleSpinReserveRequest = Body(
        ...,
        examples={
            "default": {
                "customer_id": "SR001",
                "event_start": "2099-01-03T14:00:00+00:00",
                "event_end": "2099-01-03T15:00:00+00:00",
                "base_kw": 1500,
                "event_kw": 900,
                "buffer_before_minutes": 10,
                "buffer_after_minutes": 5,
                "awarded_capacity_kw": 1200,
                "bid_capacity_kw": 1500,
                "efficiency_level": 1,
                "is_dispatched": True,
                "capacity_price_per_kw": 0.0,
                "energy_price_per_kwh": 4.0
            }
        },
    )
):
    return generate_spin_reserve_samples(req)
