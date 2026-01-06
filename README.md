# DR API Server – 日選／保證反應／即時備轉

This repository contains a reference implementation of a **Demand Response (DR) API server** written in Python using FastAPI.  The initial goal of the service was to compute the **Customer Baseline Load (CBL)** and reward for participants in the **日選時段型 (day‑select time‑slot)** DR program as defined by Taipower.  It has since been extended to support the **保證反應型 (guaranteed response)** plan under the **即時性調整用電措施** (real‑time adjustment measures) and the **即時備轉 (spin reserve)** program.  Across these plans, the API computes event baselines, target loads, actual reductions, and settlement amounts.

## Background

According to Taipower’s official regulations, the baseline for the 日選時段型 program is calculated by averaging the participant’s demand during the same time slot across the **20 most recent qualifying days** (non‑event days, non‑off‑peak days, and weekdays)【106788555196366†L136-L143】.  This average is then **adjusted by a load‑adjustment factor**.  The load‑adjustment factor is defined as the difference between

1. the participant’s average demand from **22:00 to 24:00 (afternoon 10 to 12)** on the event day, and
2. the average demand in the same 22:00‑24:00 window across the previous 20 qualifying days【106788555196366†L141-L147】.

If this difference is negative it is treated as zero【106788555196366†L141-L147】.  Under the latest guidelines, the **final CBL (基準用電容量)** should take the **smaller** of `CBL1 + AF` and the participant’s **contract capacity (CBL2)**【164418267621156†L24-L35】.  Here `CBL1` is the 20‑day average over the event window, and `AF` is the load‑adjustment factor described above.  The implementation in `main.py` follows this logic.

## Features

- **FastAPI server** with clear, self‑documenting endpoints.
- **Stateless compute endpoints**: meter data is provided per request (15‑minute for day‑select/guaranteed, 1‑minute for spin reserve); add a database in production if needed.
- **日選時段型** CBL/reduction/reward with cross‑day AF (22:00–24:00) and contract‑capacity caps.
- **保證反應型** baseline, event reduction, and monthly settlement with execution‑rate‑based incentives and penalties.
- **即時備轉** baseline, reduction, and monthly settlement with service‑quality‑weighted fees.
- **Required‑records helpers and sample generators** plus bundled JSON samples.

## Requirements

- Python 3.9 or later
- [`fastapi`](https://fastapi.tiangolo.com/) and [`uvicorn`](https://www.uvicorn.org/)
- [`pydantic`](https://docs.pydantic.dev/) and [`pytz`](https://pytz.sourceforge.net/)

Install dependencies with pip:

```bash
pip install -r requirements.txt
```

## Running the server

Place `main.py` at the root of your project, then start the development server with:

```bash
uvicorn main:app --reload --port 18000
```

The service will listen on `http://localhost:18000/` with the command above.  Swagger/OpenAPI documentation is automatically generated and can be viewed at `http://localhost:18000/docs`.

To run with Docker:

```bash
docker compose up --build
```

## Data requirements and required‑records helpers

- Day‑select and guaranteed plans use 15‑minute records; spin reserve uses 1‑minute records.
- `required-records` endpoints return `required_days` (full‑day 15‑minute) for day‑select/guaranteed, and `windows` with `granularity_seconds` for spin reserve.
- Window validation uses (start, end] semantics; send full‑day data for listed dates and the API will slice the needed windows (事件時段、22:00‑24:00 for AF；事件日未提供 22‑24 時段則 AF 視為 0).
- Extra records are ignored; duplicates or misaligned timestamps are rejected.
- Day‑select required‑records endpoints accept `min_baseline_days` (default 20) for shorter tests.

Example `required_days` (日選 CBL):
```json
{
  "customer_id": "C001",
  "required_days": [
    {"date": "2025-06-03", "role": "baseline"},
    … (18 more baseline) …,
    {"date": "2025-06-30", "role": "baseline"},
    {"date": "2025-07-01", "role": "event"}
  ]
}
```

Example monthly settlement request (日選):
```json
{
  "customer_id": "C001",
  "contract_capacity_kw": 120,
  "committed_capacity_kw": 100,
  "dr_periods": [{"start": "2025-07", "end": "2025-10"}],
  "records": [ /* full-day 15-min data for baseline + all event days */ ],
  "events": [
    {
      "event_start": "2025-07-01T16:00:00+08:00",
      "event_end": "2025-07-01T22:00:00+08:00",
      "batch_time_tariff": false
    },
    {
      "event_start": "2025-07-08T16:00:00+08:00",
      "event_end": "2025-07-08T22:00:00+08:00",
      "batch_time_tariff": false
    }
  ]
}
```

## API Endpoints

All compute endpoints take meter data inline (`records: [...]`). Validation rules:
- Day‑select/guaranteed require 15‑minute alignment; spin reserve requires 1‑minute alignment; no duplicates per customer.
- 送入 `required_days` 列出的「整日」15 分鐘資料（起始不含、結束含），API 會自動挑出需要的視窗並檢查缺漏。
- 即時備轉依 `windows` 回傳的時間窗與 `granularity_seconds` 送入資料（分鐘級）。
- 多餘資料不會被拒絕。

### `POST /dr/day-select/cbl`

Compute the CBL for a given DR event.  The request body must include:

- `customer_id` – ID of the customer
- `event_start` – start time of the DR event (ISO 8601 with time zone)
- `event_end`   – end time of the DR event (must be later than the start time)
- `batch_time_tariff` – whether to use the batch-time tariff window (fixed 15:30–21:30)
- `records` – 15-minute meter records covering `required_days`（整日 15 分鐘，起始不含、結束含）；系統會自動擷取事件時段與 22:00–24:00 所需片段。
- `contract_capacity_kw` – the participant’s contract capacity in kW (CBL2).  The final CBL is the smaller of `CBL1 + AF` and this contract capacity
- `committed_capacity_kw` – committed reduction capacity (used to compute the target load)
- `dr_periods` – list of contract DR periods, each with `start`/`end` (YYYY-MM or YYYY-MM-DD). Event day must lie within one of these periods.
- Optional: `assumed_af_kw` – if computing before the event and you do not have event-day 22:00–24:00 data, provide an assumed average (used for AF); otherwise AF uses actual data.


When called, the endpoint will:

1. Verify the event day falls within one of the provided DR periods and allowed time windows.
2. Locate the 20 most recent qualifying days prior to the event (start‑exclusive/end‑inclusive, excluding weekends、離峰日、任何抑低期間內的日期)，回溯至上一個 11/1。
3. Compute the 20‑day average demand over the event’s time window.
4. Compute the load‑adjustment factor using the 22:00–24:00 window.
5. Return a JSON response containing the baseline kW, the list of dates used as baseline sources and intermediate calculation details.

Example using the bundled sample data:

```bash
jq '{
  customer_id: "C001",
  event_start: "2025-07-01T16:00:00+08:00",
  event_end: "2025-07-01T22:00:00+08:00",
  batch_time_tariff: false,
  contract_capacity_kw: 120,
  committed_capacity_kw: 80,
  dr_periods: [{start: "2025-07", end: "2025-10"}],
  records: .records
}' sample_meter_data.json > day_select_cbl.json

curl -X POST http://localhost:18000/dr/day-select/cbl \
     -H "Content-Type: application/json" \
     --data @day_select_cbl.json
```


Sample response (your numbers may differ depending on your data):

```json
{
  "customer_id": "C001",
  "event_start": "2025-07-01T16:00:00+08:00",
  "event_end": "2025-07-01T22:00:00+08:00",
  "cbl_kw": 99.91,
  "target_load_kw": 19.91,
  "baseline_source_days": [
    "2025-06-03",
    "2025-06-04",
    … (18 more dates) …
  ],
  "method": "day-select-cbl-v1",
  "detail": {
    "cbl1_kw": 99.91,
    "af_kw": 0.00,
    "cbl1_plus_af_kw": 99.91,
    "cbl2_kw": 120.0,
    "cbl_kw": 99.91,
    "hist_adjust_avg_kw": 99.89,
    "today_adjust_avg_kw": 79.97
  }
}
```

### `POST /dr/day-select/reduction`

This endpoint computes the **single-event reward** (含 CBL/AF、實際抑低、執行率/減載比率與費率)。建議先呼叫 `/dr/day-select/reduction/required-records` 取得需求「整日」列表，再提交整日 15 分鐘資料。

Steps:
1. Compute CBL (same as `/dr/day-select/cbl`，AF 若事件日 22–24 缺資料則為 0)。
2. Compute actual reduction = `max(cbl_kw − event_avg_kw, 0)`。
3. Execution rate = actual_reduction ÷ committed_capacity（四檔減載比率 0/0.8/1.0/1.2，x 取一位小數、上限 1.2）。
4. Tariff by event duration (2/4/6 hr → 2.47/1.84/1.69 NTD/kWh)，reward = committed_capacity × execution_rate × hours × tariff × reduction_ratio。

Request fields: 同原 reduction（但回傳為回饋金計算結果）。

Response fields: 同單次 settlement（`cbl_kw`, `target_load_kw`, `actual_avg_kw`, `actual_reduction_kw`, `execution_rate`, `reduction_ratio`, `tariff_rate`, `event_duration_hours`, `reward_ntd`, `detail` 等）。

### Batch production time tariff (批次生產時間電價)

For participants opting into the batch production time tariff, the event window is fixed to **15:30–21:30** (`batch_time_tariff: true`). Two ready-to-use samples are included:

```bash
curl -X POST http://localhost:18000/dr/day-select/cbl \
  -H "Content-Type: application/json" \
  --data @samples/day_select_batch_cbl_correct.json

curl -X POST http://localhost:18000/dr/day-select/reduction \
  -H "Content-Type: application/json" \
  --data @samples/day_select_batch_reward_correct.json
```

Both samples contain complete 15-minute data for the required 15:30–21:30 window.

## Demonstration Dataset

`sample_meter_data.json` contains 15-minute data for `C001` covering 20 baseline weekdays plus the event day (event window 16:00–22:00, adjustment window 22:00–24:00). Use it directly—no batch upload endpoint is needed.

Quick test:

```bash
uvicorn main:app --reload --port 18000

jq '{
  customer_id: "C001",
  event_start: "2025-07-01T16:00:00+08:00",
  event_end: "2025-07-01T22:00:00+08:00",
  batch_time_tariff: false,
  contract_capacity_kw: 120,
  committed_capacity_kw: 100,
  dr_periods: [{start: "2025-07", end: "2025-10"}],
  records: .records
}' sample_meter_data.json > day_select_reward.json

curl -X POST http://localhost:18000/dr/day-select/reduction \
     -H "Content-Type: application/json" \
     --data @day_select_reward.json
```


### `POST /dr/day-select/settlement`

Compute the **monthly settlement** for the day-select plan. This aggregates multiple events, each using the single-event reward formula (CBL + AF + execution rate/reduction ratio + tariff by 2/4/6 hr).  This endpoint builds upon the CBL calculation and applies Taipower’s reward formula for the day‑select plan:

1. Compute the CBL using the same logic as `/dr/day-select/cbl`.
2. Determine the **actual reduction** as the difference between the CBL and the customer’s average demand during the event window (negative values are treated as zero).
3. Calculate the **execution rate** `x` as `(actual reduction) / (committed reduction capacity)`.  Round `x` to one decimal place and cap it at 120%【740316401331464†L231-L235】.
4. Determine the **reduction ratio** according to Taipower’s table:
   - `x < 60%`: 0 (no reward)
   - `60% ≤ x < 80%`: 0.8
   - `80% ≤ x < 95%`: 1.0
   - `x ≥ 95%`: 1.2【740316401331464†L243-L253】
5. Choose the **tariff reduction rate** based on the event duration (2 hr → 2.47; 4 hr → 1.84; 6 hr → 1.69 NTD/kWh)【740316401331464†L255-L265】.
6. Compute the reward: `committed_reduction_capacity × execution_rate × event_duration_hours × tariff_rate × reduction_ratio`【740316401331464†L231-L235】.

Request fields:

- `customer_id` – ID of the customer
- `contract_capacity_kw` – the customer’s contract capacity (CBL2) used in the CBL calculation
- `committed_capacity_kw` – the monthly committed reduction capacity (約定抑低契約容量); events may override
- `dr_periods` – list of contract DR periods, each with `start`/`end` (YYYY-MM or YYYY-MM-DD)
- `records` – 15-minute meter records covering all baseline + event days for the month
- `events` – list of events with `event_start`, `event_end`, `batch_time_tariff`, optional `assumed_af_kw`, and optional `committed_capacity_kw`

Example (using the bundled monthly sample):

```bash
curl -X POST http://localhost:18000/dr/day-select/settlement \
     -H "Content-Type: application/json" \
     --data @samples/day_select_settlement_monthly.json
```

Sample response (numbers will vary with your data):

```json
{
  "customer_id": "C001",
  "contract_capacity_kw": 120.0,
  "committed_capacity_kw": 100.0,
  "total_reward_ntd": 0.0,
  "total_actual_reduction_kwh": 63.36,
  "events": [
    {
      "customer_id": "C001",
      "event_start": "2025-07-01T16:00:00+08:00",
      "event_end": "2025-07-01T22:00:00+08:00",
      "committed_capacity_kw": 100.0,
      "cbl_kw": 99.91,
      "target_load_kw": -0.09,
      "actual_avg_kw": 89.35,
      "actual_reduction_kw": 10.56,
      "execution_rate": 0.1,
      "reduction_ratio": 0.0,
      "tariff_rate": 1.69,
      "event_duration_hours": 6.0,
      "reward_ntd": 0.0,
      "baseline_source_days": [
        "2025-06-03",
        …
      ],
      "method": "day-select-reward-v1",
      "detail": {
        "cbl1_kw": 99.91,
        "af_kw": 0.00,
        "cbl1_plus_af_kw": 99.91,
        "cbl2_kw": 120.0,
        "cbl_kw": 99.91,
        "hist_adjust_avg_kw": 99.89,
        "today_adjust_avg_kw": 79.97,
        "actual_avg_kw": 89.35,
        "actual_reduction_kw": 10.56,
        "execution_rate_ratio": 0.1,
        "reduction_ratio": 0.0,
        "tariff_rate": 1.69,
        "event_duration_hours": 6.0,
        "reward_ntd": 0.0,
        "target_load_kw": -0.09
      }
    }
  ],
  "method": "day-select-settlement-monthly-v1"
}
```

## Variable Definitions

The API responses include several fields and intermediate values.  Here is a concise definition of each key variable used in the CBL and reward calculations:

- **`CBL1`** – The 20‑day average demand across the DR event’s time window【106788555196366†L136-L143】.
- **`AF` (Load‑Adjustment Factor)** – The difference between the event‑day average demand in the 22:00–24:00 window and the 20‑day historical average of the same window【106788555196366†L141-L147】; if the difference is negative, it is treated as zero【106788555196366†L141-L147】.
- **`CBL2`** – The participant’s **contract capacity** (經常契約容量).  The final baseline will not exceed this value.【164418267621156†L24-L35】
- **`cbl_kw` (Final CBL)** – The **minimum** of `CBL1 + AF` and `CBL2`【164418267621156†L24-L35】.  This is the baseline used to determine the actual reduction.
- **`target_load_kw`** – `cbl_kw − committed_capacity_kw`, the target load after the committed reduction.
- **`cbl1_kw`, `af_kw`, `cbl1_plus_af_kw`, `cbl2_kw`** – Internal values returned in the `detail` field representing `CBL1`, `AF`, their sum, and the contract capacity, respectively.
- **`hist_adjust_avg_kw`** – The 20‑day historical average demand during the 22:00–24:00 window (used to compute `AF`).
- **`today_adjust_avg_kw`** – The event‑day average demand during the 22:00–24:00 window.
- **`actual_avg_kw`** – The participant’s actual average demand during the event window.  It is used to compute the actual reduction.
- **`actual_reduction_kw`** – The difference between `cbl_kw` and `actual_avg_kw`.  If this value is negative, it is set to zero (no reduction).
- **`execution_rate` / `execution_rate_ratio`** – The ratio of `actual_reduction_kw` to the committed reduction capacity.  It is rounded to one decimal place and capped at **1.2 (120%)**【740316401331464†L231-L235】.
- **`reduction_ratio`** – A multiplier applied to the reward.  According to Taipower’s rules, it takes values of **0**, **0.8**, **1.0**, or **1.2** depending on the execution rate【740316401331464†L243-L253】.
- **`tariff_rate`** – The per‑kWh reward rate chosen based on the event duration: **2.47 NTD/kWh** for 2‑hour events, **1.84 NTD/kWh** for 4‑hour events, and **1.69 NTD/kWh** for 6‑hour events【740316401331464†L255-L265】.
- **`event_duration_hours`** – The length of the DR event in hours (2, 4 or 6).
- **`reward_ntd`** – The calculated daily electricity‑fee deduction (回饋金) in New Taiwan Dollars.  It is computed as:

  \[\text{reward}\_\text{ntd} = \text{committed}\_\text{capacity}\_\text{kw} \times \text{execution}\_\text{rate} \times \text{event}\_\text{duration}\_\text{hours} \times \text{tariff}\_\text{rate} \times \text{reduction}\_\text{ratio}\]【740316401331464†L231-L235】.

- **`customer_id`** – Identifier for a participant.  Meter data and DR events are grouped by this ID.
- **`event_start` / `event_end`** – The start and end timestamps of the DR event (ISO 8601 with time zone).  The difference between them must be 2, 4 or 6 hours.
- **`contract_capacity_kw`** – The participant’s contract capacity in kW (CBL2).  Affects the final baseline.
- **`committed_capacity_kw`** – The participant’s **committed reduction capacity** (約定抑低契約容量) used to compute the execution rate and reward.

## Extending the Server

The current implementation covers day‑select, guaranteed response, and spin reserve calculations.  In a production system you may wish to extend the server with:

- **Persistent storage** (e.g. TimescaleDB or PostgreSQL) for meter data.
- **Additional DR plans** such as the 月選8日型 or 即時性 adjustments【106788555196366†L134-L147】.
- **Electricity‑fee deduction calculations** based on the calculated CBL and participant’s contract capacity【106788555196366†L154-L182】.
- **User authentication** and multi‑tenant support for different customers.

By building on this foundation, you can create a complete DR management platform that complies with Taipower’s regulations and provides participants with transparent and auditable baseline calculations.

## Guaranteed Response Plan (保證反應型)

In addition to the day‑select plan, the API also supports Taipower’s **保證反應型** (guaranteed response) program under the 即時性調整用電措施.  Participants in this program commit to reduce a fixed capacity when notified and are rewarded (or penalized) based on their performance over a month【574061540680747†L208-L238】【574061540680747†L240-L253】.

### Baseline and Reduction Calculation

For each guaranteed response event:

1. **Notification and event duration** – Taipower may notify participants **30, 60 or 120 minutes** before the event.  Events may last **2 hours**, **3 hours** or **4 hours**【574061540680747†L208-L238】.
2. **Baseline (基準用電)** – The baseline is defined as the average demand during the **two hours immediately before the notification time**【574061540680747†L208-L238】.  The server computes this average using 15‑minute records.
3. **Actual reduction** – The reduction is the difference between the baseline and the participant’s average demand during the event window.  If this value is negative, it is set to zero【574061540680747†L235-L238】.
4. **Execution rate** – The ratio of the actual reduction to the participant’s **committed reduction capacity** (約定抑低契約容量).  It is rounded to one decimal place and capped at **1.0 (100%)**【574061540680747†L258-L272】.

Validation notes:
- Event start must be 13:00–22:00 on a weekday/non‑off‑peak day, duration 2/3/4 hours.
- `contract_capacity_kw` must be ≥ 1,000; `committed_capacity_kw` must be ≥ max(1,000, 15% of contract) and ≤ contract capacity.
- Event day must fall within one of the supplied `dr_periods`.

### Fee Reduction and Penalty Rules

The monthly fee adjustment consists of a **basic fee reduction** and a **flow fee reduction**, minus any **extra charges**:

- **Basic fee reduction** – Calculated from the contract capacity and a basic fee rate (NTD per kW per month).  The rate depends on the notification advance time (93 for 30 min, 84 for 60 min, 78 for 120 min)【574061540680747†L240-L253】.  A reduction ratio is applied based on the **average execution rate** across all events in the month:
  - Average execution < 70 % → ratio = 0
  - 70 % ≤ average < 80 % → ratio = 0.6
  - 80 % ≤ average < 95 % → ratio = 0.8
  - Average ≥ 95 % → ratio = 1.0【574061540680747†L258-L272】
- **Flow fee reduction** – For each event, if the execution rate ≥ 70 %, the participant receives a reduction equal to **actual reduction × event duration × flow fee rate** (default flow fee rate is 12 NTD per kWh)【574061540680747†L282-L286】.  Otherwise, the flow reduction is zero.
- **Extra charge** – If an event’s execution rate < 60 %, the participant is charged: 

  \[(1 − \text{execution_rate}) × \text{committed_capacity_kw} × \text{event_duration_hours} × \text{flow_fee_rate} × 2\]

  This penalty doubles the flow fee rate and applies to the portion of the committed capacity that was not met【574061540680747†L288-L291】.
- **No events** – If no events are notified in a month, the basic fee reduction defaults to **contract_capacity × basic_fee_rate**【574061540680747†L295-L297】.

### Endpoints

The guaranteed response plan exposes CBL, single‑event reduction, and monthly settlement endpoints (plus required‑records helpers).

#### `POST /dr/guaranteed/cbl`

Compute the baseline (two‑hour pre‑notification average) for a single guaranteed response event.  Use this endpoint **before** dispatch to determine the participant’s typical load without the need for actual event data.

Request fields:

- `customer_id` – ID of the participant.
- `event_start` / `event_end` – scheduled start/end time of the event (ISO 8601). Duration must be 2, 3 or 4 hours.
- `notification_minutes_before` – minutes of advance notice (30, 60 or 120).
- `contract_capacity_kw` – the participant’s contract capacity (kW).
- `committed_capacity_kw` – the committed reduction capacity (required).
- `dr_periods` – list of contract DR periods (`start`/`end`, YYYY-MM or YYYY-MM-DD); event day must fall within one of them.
- `records` – 15‑minute meter records covering the notification window.

The response returns the baseline kW and the time window used for the calculation.

#### `POST /dr/guaranteed/reduction`

Compute the baseline and **actual reduction** for a single guaranteed response event.  This endpoint should be used **after** the event has occurred.  The request body must include:

- `customer_id` – ID of the participant.
- `event_start` / `event_end` – start and end timestamps of the event (ISO 8601).  The difference between them must be 2, 3 or 4 hours.
- `notification_minutes_before` – minutes of advance notice (30, 60 or 120).
- `contract_capacity_kw` – the participant’s contract capacity (kW).
- `committed_capacity_kw` – the committed reduction capacity (約定抑低契約容量).
- `dr_periods` – list of contract DR periods (`start`/`end`, YYYY-MM or YYYY-MM-DD).
- `records` – 15‑minute meter records covering the event day.
- Optional: `basic_fee_rate` and `flow_fee_rate` – override the default rates.

The response returns the baseline kW, the actual average demand and reduction, the execution rate, and the flow fee reduction or extra charge for that event.

#### `POST /dr/guaranteed/settlement`

Compute the **monthly electricity‑fee adjustment** for a guaranteed response participant.  The request body must include:

- `customer_id` – ID of the participant.
- `notification_minutes_before` – the standard advance notice for the month (30, 60 or 120).
- `contract_capacity_kw` – the participant’s contract capacity (kW).
- `committed_capacity_kw` – the monthly committed reduction capacity (required).
- `dr_periods` – list of contract DR periods (`start`/`end`, YYYY-MM or YYYY-MM-DD); all event days must fall within one of them.
- `events` – a list of objects describing each event in the month (each object must include `customer_id`, `event_start`, `event_end`, and optional `committed_capacity_kw`).
- `records` – 15-minute meter records covering the event dates listed in `required_days`（整日 15 分鐘），系統會自動擷取通知前 2 小時與事件時段。
- Optional: `basic_fee_rate` and `flow_fee_rate` – override the default rates for all events.

The endpoint calculates, for each event, the baseline, reduction, execution rate, flow reduction and extra charge.  It then computes the average execution rate for the month, applies the appropriate reduction ratio to the basic fee, sums the flow reductions and extra charges, and returns the net reward.

### Variables for the Guaranteed Response Plan

- **`baseline_kw`** – The average demand during the 2‑hour window preceding the notification time【574061540680747†L208-L238】.
- **`actual_avg_kw`** – The average demand during the event window.
- **`actual_reduction_kw`** – `max(baseline_kw − actual_avg_kw, 0)`【574061540680747†L235-L238】.
- **`target_load_kw`** – `baseline_kw − committed_capacity_kw`, the target load after the committed reduction.
- **`execution_rate`** – `(actual_reduction_kw / committed_capacity_kw)`, rounded to one decimal place and capped at 1.0 (100%)【574061540680747†L258-L272】.
- **`event_duration_hours`** – Length of the event in hours (2, 3 or 4).
- **`flow_reduction_amount`** – For each event, if `execution_rate ≥ 0.7`, equals `actual_reduction_kw × event_duration_hours × flow_fee_rate`; otherwise zero【574061540680747†L282-L286】.
- **`extra_charge_amount`** – For each event, if `execution_rate < 0.6`, equals `(1 − execution_rate) × committed_capacity_kw × event_duration_hours × flow_fee_rate × 2`; otherwise zero【574061540680747†L288-L291】.
- **`average_execution_rate`** – The average of all event execution rates across the month.
- **`reduction_ratio`** – Multiplier for the basic fee reduction based on the average execution rate (0, 0.6, 0.8 or 1.0)【574061540680747†L258-L272】.
- **`basic_fee_rate`** – The monthly fee rate per kW, determined by the notification advance time (93, 84 or 78 NTD/kW)【574061540680747†L240-L253】.
- **`flow_fee_rate`** – The per‑kWh flow fee rate (default 12 NTD/kWh)【574061540680747†L240-L253】.
- **`basic_reduction_amount`** – `contract_capacity_kw × basic_fee_rate × reduction_ratio` (or `contract_capacity_kw × basic_fee_rate` if no events occurred)【574061540680747†L295-L297】.
- **`flow_reduction_total_amount`** – Sum of `flow_reduction_amount` across all events in the month.
- **`extra_charge_total_amount`** – Sum of `extra_charge_amount` across all events.
- **`net_reward_amount`** – `basic_reduction_amount + flow_reduction_total_amount − extra_charge_total_amount`.

## Spin Reserve (即時備轉)

The spin reserve workflow uses 1‑minute records and a 5‑minute pre‑dispatch baseline.

### Baseline and Settlement Logic

1. Baseline (CBL) = average kW over the 5 minutes before `event_start` (1‑minute granularity).
2. Actual reduction = `max(baseline − event average, 0)`.
3. Execution rate (dispatched) = `actual_reduction / awarded_capacity`; standby rate (not dispatched) = `baseline / awarded_capacity`; both capped at 1.0.
4. Service quality index (SQI) uses execution rate (or standby rate if not dispatched): ≥ 0.95 → 1.0, ≥ 0.85 → 0.7, ≥ 0.7 → 0.0, else −1.0.
5. Fees: `capacity_fee = awarded_capacity × capacity_price_per_kw × hours`, `efficiency_fee = awarded_capacity × efficiency_price(level 1/2/3 = 0.10/0.06/0.04) × hours`, `energy_fee = actual_reduction × hours × energy_price` (only if dispatched). Total = capacity_fee + efficiency_fee × SQI + energy_fee.
   If `energy_price_per_kwh` is omitted, the API uses a default estimate.

### Endpoints

- `POST /dr/spin-reserve/cbl/required-records` – returns the 5‑minute baseline window (`granularity_seconds: 60`).
- `POST /dr/spin-reserve/cbl` – computes baseline using 1‑minute records; validates `awarded_capacity_kw ≤ bid_capacity_kw`.
- `POST /dr/spin-reserve/reduction/required-records` – returns baseline + event windows.
- `POST /dr/spin-reserve/reduction` – computes reduction, service quality index, and fees (`awarded_capacity_kw`, `efficiency_level`, `is_dispatched`).
- `POST /dr/spin-reserve/settlement/required-records` – returns windows for each event.
- `POST /dr/spin-reserve/settlement` – aggregates multiple events into `total_fee`.

## Samples

Sample payloads live in `samples/`:
- Day-select CBL pre-event: `samples/day_select_cbl_correct.json` (valid; uses `assumed_af_kw`, baseline-only records) and `samples/day_select_cbl_wrong.json` (invalid: missing a baseline slot).
- Day-select reward/reduction post-event: `samples/day_select_reward_correct.json` (valid) and `samples/day_select_reward_wrong.json` (invalid: missing an event-window slot).
- Day-select monthly settlement: `samples/day_select_settlement_monthly.json` (valid; multiple events, shared records list).
- Guaranteed CBL pre-event: `samples/guaranteed_cbl_correct.json` (valid) and `samples/guaranteed_cbl_wrong.json` (invalid: misaligned timestamp).
- Guaranteed reward/reduction post-event: `samples/guaranteed_reward_correct.json` (valid) and `samples/guaranteed_reward_wrong.json` (invalid: missing an event-window slot).

Sample record generators are also available via the API: `/dr/day-select/sample-records`, `/dr/guaranteed/sample-records`, and `/dr/spin-reserve/sample-records` (1‑minute data).

Quick calls:

```bash
# Day-select CBL (pre-event, assumed adjust)
curl -X POST http://localhost:18000/dr/day-select/cbl \
  -H "Content-Type: application/json" \
  --data @samples/day_select_cbl_correct.json

# Day-select reward (post-event)
curl -X POST http://localhost:18000/dr/day-select/reduction \
  -H "Content-Type: application/json" \
  --data @samples/day_select_reward_correct.json

# Day-select monthly settlement
curl -X POST http://localhost:18000/dr/day-select/settlement \
  -H "Content-Type: application/json" \
  --data @samples/day_select_settlement_monthly.json

# Guaranteed CBL (pre-event)
curl -X POST http://localhost:18000/dr/guaranteed/cbl \
  -H "Content-Type: application/json" \
  --data @samples/guaranteed_cbl_correct.json

# Guaranteed reward (post-event)
curl -X POST http://localhost:18000/dr/guaranteed/reduction \
  -H "Content-Type: application/json" \
  --data @samples/guaranteed_reward_correct.json
```

## Sample Calls and Expected Results

- `samples/day_select_cbl_correct.json` → `POST /dr/day-select/cbl`: 200 OK. `cbl_kw` ~100 (AF ≈ 0 because assumed_af_kw=95 is below hist adjust). Baseline dates list returned.
- `samples/day_select_cbl_wrong.json` → `POST /dr/day-select/cbl`: 400 with message like `缺少 ... 15 分鐘區間` (baseline window gap).
- `samples/day_select_reward_correct.json` → `POST /dr/day-select/reduction`: 200 OK. `cbl_kw` ~100; event avg < baseline so positive `actual_reduction_kw`; execution_rate based on committed=100.
- `samples/day_select_reward_wrong.json` → `POST /dr/day-select/reduction`: 400 with message like `事件日 ... 缺少 ... 15 分鐘區間` (event window gap).
- `samples/day_select_settlement_monthly.json` → `POST /dr/day-select/settlement`: 200 OK. Returns `total_reward_ntd`, `total_actual_reduction_kwh`, and per-event `events`.
- `samples/guaranteed_cbl_correct.json` → `POST /dr/guaranteed/cbl`: 200 OK. `baseline_kw` ~100 (average of 08:00–10:00).
- `samples/guaranteed_cbl_wrong.json` → `POST /dr/guaranteed/cbl`: 400 with message like `時間戳未對齊 15 分鐘`.
- `samples/guaranteed_reward_correct.json` → `POST /dr/guaranteed/reduction`: 200 OK. `baseline_kw` ~100, event avg ~30 → reduction ~70, execution_rate ~0.8 on committed=90; flow reduction positive, no penalty.
- `samples/guaranteed_reward_wrong.json` → `POST /dr/guaranteed/reduction`: 400 with message like `缺少 ... 15 分鐘區間` (event window gap).
