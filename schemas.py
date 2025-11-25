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


class DaySelectCBLRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    batch_time_tariff: bool = Field(False, description="是否選用批次生產時間電價（固定 15:30-21:30）")
    assumed_af_kw: Optional[float] = Field(
        None, description="若在事件前計算 CBL，可預估事件日 22:00-24:00 平均需量（用於 AF），未提供則以 0 計算 AF"
    )
    records: List[MeterRecord]
    contract_capacity_kw: Optional[float] = None


class DaySelectCBLResponse(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    cbl_kw: float
    baseline_source_days: List[date]
    method: str
    detail: Dict[str, Any]


class DaySelectRewardRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    batch_time_tariff: bool = Field(False, description="是否選用批次生產時間電價（固定 15:30-21:30）")
    assumed_af_kw: Optional[float] = Field(
        None, description="事件前可預估 22:00-24:00 平均需量（用於 AF）；未提供則 AF 預設 0"
    )
    records: List[MeterRecord]
    contract_capacity_kw: Optional[float] = None
    committed_capacity_kw: float


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
    baseline_source_days: List[date]
    method: str
    detail: Dict[str, Any]


class DaySelectReductionRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    batch_time_tariff: bool = Field(False, description="是否選用批次生產時間電價（固定 15:30-21:30）")
    assumed_af_kw: Optional[float] = Field(
        None, description="事件前可預估 22:00-24:00 平均需量（用於 AF）；未提供則 AF 預設 0"
    )
    records: List[MeterRecord]
    contract_capacity_kw: Optional[float] = None
    committed_capacity_kw: Optional[float] = None


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
    committed_capacity_kw: Optional[float] = Field(
        None, description="約定抑低契約容量，未提供則以 contract_capacity_kw 為準"
    )
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
    detail: Dict[str, Any]


class GuaranteedRewardEvent(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    committed_capacity_kw: Optional[float] = Field(
        None, description="事件約定抑低契約容量，未提供則套用月度或契約容量"
    )


class GuaranteedRewardRequest(BaseModel):
    customer_id: str
    notification_minutes_before: int = Field(..., description="通知提前分鐘數，30、60 或 120")
    contract_capacity_kw: float = Field(..., gt=0, description="抑低契約容量 (瓩)")
    events: List[GuaranteedRewardEvent] = Field(
        ..., description="本月所有抑低事件清單，每項事件需包含開始與結束時間"
    )
    committed_capacity_kw: Optional[float] = Field(
        None, description="月度約定抑低契約容量，事件未提供時沿用，否則退回契約容量"
    )
    records: List[MeterRecord]
    basic_fee_rate: Optional[float] = None
    flow_fee_rate: Optional[float] = None


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


class GuaranteedCBLRequest(BaseModel):
    customer_id: str
    event_start: datetime
    records: List[MeterRecord]
    notification_minutes_before: int = Field(..., description="通知提前分鐘數，30、60 或 120")
    contract_capacity_kw: float = Field(..., gt=0, description="抑低契約容量 (瓩)")


class GuaranteedCBLResponse(BaseModel):
    customer_id: str
    event_start: datetime
    notification_minutes_before: int
    baseline_kw: float
    detail: Dict[str, Any]


# 新增：需求視窗查詢
class RequiredWindow(BaseModel):
    label: str
    start: datetime
    end: datetime
    optional: bool = False


class DaySelectRequiredRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    batch_time_tariff: bool = False
    min_baseline_days: int = 20


class DaySelectRequiredResponse(BaseModel):
    customer_id: str
    baseline_days: List[date]
    windows: List[RequiredWindow]


class GuaranteedRequiredRequest(BaseModel):
    customer_id: str
    event_start: datetime
    event_end: datetime
    notification_minutes_before: int


class GuaranteedRequiredResponse(BaseModel):
    customer_id: str
    windows: List[RequiredWindow]


# 新增：區分前/後階段需求
class DaySelectRequiredPreResponse(DaySelectRequiredResponse):
    pass


class DaySelectRequiredPostResponse(BaseModel):
    customer_id: str
    windows: List[RequiredWindow]


class GuaranteedRequiredPreResponse(GuaranteedRequiredResponse):
    pass


class GuaranteedRequiredPostResponse(BaseModel):
    customer_id: str
    windows: List[RequiredWindow]
