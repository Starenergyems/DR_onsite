from datetime import datetime, date
from typing import List, Dict, Optional, Any

from pydantic import BaseModel, Field


# -------------------------
# Pydantic Models
# -------------------------
class MeterRecord(BaseModel):
    customer_id: str
    timestamp: datetime
    kw: float = Field(..., ge=0)


class DRPeriod(BaseModel):
    start: str = Field(..., description="抑低期間起日，格式 YYYY-MM 或 YYYY-MM-DD")
    end: str = Field(..., description="抑低期間迄日，格式 YYYY-MM 或 YYYY-MM-DD")


class DaySelectCBLRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    batch_time_tariff: bool = Field(..., description="是否選用批次生產時間電價（固定 15:30-21:30）")
    assumed_af_kw: Optional[float] = Field(
        None, description="若在事件前計算 CBL，可預估事件日 22:00-24:00 平均需量（用於 AF），未提供則以 0 計算 AF"
    )
    records: List[MeterRecord]
    contract_capacity_kw: float
    committed_capacity_kw: float = Field(..., description="約定抑低契約容量，用於目標負載計算")
    dr_periods: List[DRPeriod] = Field(..., description="與台電簽訂的抑低期間清單，起訖含當日")


class DaySelectCBLResponse(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    cbl_kw: float
    target_load_kw: float
    baseline_source_days: List[date]
    method: str
    detail: Dict[str, Any]


class DaySelectRewardRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    batch_time_tariff: bool = Field(..., description="是否選用批次生產時間電價（固定 15:30-21:30）")
    assumed_af_kw: Optional[float] = Field(
        None, description="事件前可預估 22:00-24:00 平均需量（用於 AF）；未提供則 AF 預設 0"
    )
    records: List[MeterRecord]
    contract_capacity_kw: float
    committed_capacity_kw: float
    dr_periods: List[DRPeriod] = Field(..., description="與台電簽訂的抑低期間清單，起訖含當日")


class DaySelectRewardResponse(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    committed_capacity_kw: float
    cbl_kw: float
    actual_avg_kw: float
    actual_reduction_kw: float
    execution_rate: float
    reduction_ratio: float
    tariff_rate: float
    event_duration_hours: float
    reward_ntd: float
    target_load_kw: float
    baseline_source_days: List[date]
    method: str
    detail: Dict[str, Any]

class DaySelectMonthlyEvent(BaseModel):
    event_start: datetime
    event_end: datetime
    batch_time_tariff: bool
    assumed_af_kw: Optional[float] = Field(None, description="事件前可預估 22:00-24:00 平均需量（用於 AF）")
    committed_capacity_kw: Optional[float] = Field(None, description="事件層級約定抑低容量，未提供則用月度值")


class DaySelectMonthlySettlementRequest(BaseModel):
    customer_id: str
    contract_capacity_kw: float
    committed_capacity_kw: float
    dr_periods: List[DRPeriod]
    records: List[MeterRecord]
    events: List[DaySelectMonthlyEvent]


class DaySelectMonthlySettlementResponse(BaseModel):
    customer_id: str
    contract_capacity_kw: float
    committed_capacity_kw: float
    total_reward_ntd: float
    total_actual_reduction_kwh: float
    events: List[DaySelectRewardResponse]
    method: str


class DaySelectReductionRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    batch_time_tariff: bool = Field(..., description="是否選用批次生產時間電價（固定 15:30-21:30）")
    assumed_af_kw: Optional[float] = Field(
        None, description="事件前可預估 22:00-24:00 平均需量（用於 AF）；未提供則 AF 預設 0"
    )
    records: List[MeterRecord]
    contract_capacity_kw: float
    committed_capacity_kw: float
    dr_periods: List[DRPeriod] = Field(..., description="與台電簽訂的抑低期間清單，起訖含當日")


class DaySelectReductionResponse(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    cbl_kw: float
    actual_avg_kw: float
    actual_reduction_kw: float
    committed_capacity_kw: Optional[float] = None
    execution_rate: Optional[float] = None
    reduction_ratio: Optional[float] = None
    target_load_kw: Optional[float] = None
    baseline_source_days: List[date]
    method: str
    detail: Dict[str, Any]


class GuaranteedEventRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    records: List[MeterRecord]
    notification_minutes_before: int = Field(..., description="通知提前分鐘數，值須為 30、60 或 120")
    contract_capacity_kw: float = Field(..., gt=0, description="抑低契約容量 (瓩)")
    committed_capacity_kw: float = Field(..., description="約定抑低契約容量")
    dr_periods: List[DRPeriod] = Field(..., description="與台電簽訂的抑低期間清單，起訖含當日")
    basic_fee_rate: Optional[float] = Field(
        None, description="基本電費扣減費率 (每瓩每月)，若未提供則依通知時間預設"
    )
    flow_fee_rate: Optional[float] = Field(
        None, description="流動電費扣減費率 (每度)，若未提供則依規範預設"
    )


class GuaranteedEventDetail(BaseModel):
    event_start: datetime
    event_end: datetime
    baseline_kw: float
    actual_avg_kw: float
    actual_reduction_kw: float
    execution_rate: float
    event_duration_hours: float
    flow_reduction_amount: float
    extra_charge_amount: float
    target_load_kw: float
    detail: Dict[str, Any]


class GuaranteedEventResponse(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    baseline_kw: float
    actual_reduction_kw: float
    execution_rate: float
    event_duration_hours: float
    flow_reduction_amount: float
    extra_charge_amount: float
    target_load_kw: float
    detail: Dict[str, Any]
    method: str


class GuaranteedRewardEvent(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    committed_capacity_kw: Optional[float] = Field(
        None, description="事件約定抑低契約容量，未提供則套用月度約定容量"
    )


class GuaranteedRewardRequest(BaseModel):
    customer_id: str
    notification_minutes_before: int = Field(..., description="通知提前分鐘數，30、60 或 120")
    contract_capacity_kw: float = Field(..., gt=0, description="抑低契約容量 (瓩)")
    committed_capacity_kw: float = Field(..., description="月度約定抑低契約容量")
    events: List[GuaranteedRewardEvent] = Field(
        ..., description="本月所有抑低事件清單，每項事件需包含開始與結束時間"
    )
    records: List[MeterRecord]
    basic_fee_rate: Optional[float] = None
    flow_fee_rate: Optional[float] = None
    dr_periods: List[DRPeriod] = Field(..., description="與台電簽訂的抑低期間清單，起訖含當日")


class GuaranteedRewardResponse(BaseModel):
    customer_id: str
    contract_capacity_kw: float
    average_execution_rate: float
    reduction_ratio: float
    basic_fee_rate: float
    flow_fee_rate: float
    basic_reduction_amount: float
    flow_reduction_total_amount: float
    extra_charge_total_amount: float
    net_reward_amount: float
    event_details: List[GuaranteedEventDetail]
    method: str


class GuaranteedCBLRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    records: List[MeterRecord]
    notification_minutes_before: int = Field(..., description="通知提前分鐘數，30、60 或 120")
    contract_capacity_kw: float = Field(..., gt=0, description="抑低契約容量 (瓩)")
    committed_capacity_kw: float = Field(..., description="約定抑低契約容量")
    dr_periods: List[DRPeriod] = Field(..., description="與台電簽訂的抑低期間清單，起訖含當日")


class GuaranteedCBLResponse(BaseModel):
    customer_id: str
    event_start: datetime
    notification_minutes_before: int
    baseline_kw: float
    target_load_kw: float
    detail: Dict[str, Any]
    method: str


# 新增：需求視窗查詢
class RequiredWindow(BaseModel):
    label: str
    start: datetime
    end: datetime
    optional: bool = False


class SpinReserveRequiredRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime


class SpinReserveRequiredResponse(BaseModel):
    customer_id: str
    windows: List[RequiredWindow]


class SpinReserveCBLRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    records: List[MeterRecord]
    contract_capacity_kw: float = Field(..., gt=0, description="經常契約容量 (瓩)")
    awarded_capacity_kw: float = Field(..., gt=0, description="得標容量 (瓩)")


class SpinReserveCBLResponse(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    baseline_kw: float
    target_load_kw: float
    method: str
    detail: Dict[str, Any]


class DaySelectRequiredRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    batch_time_tariff: bool
    min_baseline_days: int = 20
    dr_periods: List[DRPeriod]


class DaySelectSettlementRequiredRequest(BaseModel):
    customer_id: str
    events: List[DaySelectMonthlyEvent]
    min_baseline_days: int = 20
    dr_periods: List[DRPeriod]


class RequiredDay(BaseModel):
    date: date
    role: str  # "baseline" or "event"


class DaySelectRequiredResponse(BaseModel):
    customer_id: str
    baseline_days: List[date]
    required_days: List[RequiredDay] = []


class GuaranteedRequiredRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    notification_minutes_before: int
    dr_periods: List[DRPeriod]


class GuaranteedSettlementRequiredRequest(BaseModel):
    customer_id: str
    events: List[GuaranteedRewardEvent]
    dr_periods: List[DRPeriod]


class GuaranteedRequiredResponse(BaseModel):
    customer_id: str
    required_days: List[RequiredDay]


# 新增：區分前/後階段需求
class DaySelectRequiredPreResponse(DaySelectRequiredResponse):
    pass


class DaySelectRequiredPostResponse(BaseModel):
    customer_id: str
    required_days: List[RequiredDay] = []


class GuaranteedRequiredPreResponse(GuaranteedRequiredResponse):
    pass


class GuaranteedRequiredPostResponse(BaseModel):
    customer_id: str
    required_days: List[RequiredDay]
