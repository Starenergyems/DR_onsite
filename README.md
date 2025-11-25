# DR API Server – 日選時段型 CBL

This repository contains a reference implementation of a **Demand Response (DR) API server** written in Python using FastAPI.  The initial goal of the service was to compute the **Customer Baseline Load (CBL)** and reward for participants in the **日選時段型 (day‑select time‑slot)** DR program as defined by Taipower.  It has since been extended to support the **保證反應型 (guaranteed response)** plan under the **即時性調整用電措施** (real‑time adjustment measures).  In both cases, the API helps determine a participant’s typical load during a DR event and calculate the actual load reduction and corresponding fee reduction.

## Background

According to Taipower’s official regulations, the baseline for the 日選時段型 program is calculated by averaging the participant’s demand during the same time slot across the **20 most recent qualifying days** (non‑event days, non‑off‑peak days, and weekdays)【106788555196366†L136-L143】.  This average is then **adjusted by a load‑adjustment factor**.  The load‑adjustment factor is defined as the difference between

1. the participant’s average demand from **22:00 to 24:00 (afternoon 10 to 12)** on the event day, and
2. the average demand in the same 22:00‑24:00 window across the previous 20 qualifying days【106788555196366†L141-L147】.

If this difference is negative it is treated as zero【106788555196366†L141-L147】.  Under the latest guidelines, the **final CBL (基準用電容量)** should take the **smaller** of `CBL1 + AF` and the participant’s **contract capacity (CBL2)**【164418267621156†L24-L35】.  Here `CBL1` is the 20‑day average over the event window, and `AF` is the load‑adjustment factor described above.  The implementation in `main.py` follows this logic.

## Features

- **FastAPI server** with clear, self‑documenting endpoints.
- **In‑memory storage** for 15‑minute metering records (kW).  In production this can be replaced by a database such as PostgreSQL or TimescaleDB.
- **CBL and reward computation** for the **日選時段型** DR plan, including handling of cross‑day intervals (22:00–24:00) for the load‑adjustment factor.
- **Baseline and fee reduction calculation** for the **保證反應型** plan, supporting per‑event baseline and monthly fee reduction computations with execution‑rate‑based incentives and penalties【574061540680747†L208-L238】【574061540680747†L240-L272】.
- **Sample dataset** and step‑by‑step instructions to demonstrate uploading meter data and retrieving computed results.

## Requirements

- Python 3.9 or later
- [`fastapi`](https://fastapi.tiangolo.com/) and [`uvicorn`](https://www.uvicorn.org/)
- [`pydantic`](https://docs.pydantic.dev/) and [`pytz`](https://pytz.sourceforge.net/)

Install dependencies with pip:

```bash
pip install fastapi uvicorn pydantic pytz
```

## Running the server

Place `main.py` at the root of your project, then start the development server with:

```bash
uvicorn main:app --reload
```

The service will listen on `http://localhost:18000/` by default.  Swagger/OpenAPI documentation is automatically generated and can be viewed at `http://localhost:18000/docs`.

## API Endpoints

All compute endpoints take meter data inline (`records: [...]`). Validation rules:
- Timestamps must align to 15‑minute boundaries; no duplicates per customer.
- Required windows must be gap‑free (baseline event windows, 22:00–24:00 windows, and event windows).
- Records outside the required windows for that request are rejected.

### `POST /dr/day-select/cbl`

Compute the CBL for a given DR event.  The request body must include:

- `customer_id` – ID of the customer
- `event_start` – start time of the DR event (ISO 8601 with time zone)
- `event_end`   – end time of the DR event (must be later than the start time)
- `records` – 15-minute meter records covering the baseline weekdays’ event windows, their 22:00–24:00 windows, and the event day’s event/22:00–24:00 windows.
- `contract_capacity_kw` – the participant’s contract capacity in kW (CBL2).  If provided, the final CBL will be the smaller of `CBL1 + AF` and this contract capacity
- Optional: `assumed_af_kw` – if computing before the event and you do not have event-day 22:00–24:00 data, provide an assumed average (used for AF); otherwise AF uses actual data.


When called, the endpoint will:

1. Verify that the event lies within the valid program window (5 May – 31 Oct)【106788555196366†L120-L128】.
2. Locate the 20 most recent qualifying days prior to the event (excluding weekends, off‑peak days and previous DR days)
3. Compute the 20‑day average demand over the event’s time window【106788555196366†L136-L143】.
4. Compute the load‑adjustment factor using the 22:00–24:00 window【106788555196366†L141-L147】.
5. Return a JSON response containing the baseline kW, the list of dates used as baseline sources and intermediate calculation details.

Example using the bundled sample data:

```bash
jq '{
  customer_id: "C001",
  event_start: "2025-07-01T16:00:00+08:00",
  event_end: "2025-07-01T22:00:00+08:00",
  contract_capacity_kw: 120,
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

This endpoint computes the **actual load reduction** for a day‑select DR event without applying any fee formula.  It should be used **after** the dispatch instruction has been executed, once actual event demand data is available.

The server performs the following steps:

1. Compute the baseline (CBL) using the same logic as `/dr/day-select/cbl`.
2. Calculate the participant’s **actual average demand** during the event window.
3. Compute the **actual reduction** as `max(cbl_kw − actual_avg_kw, 0)`.

Request fields:

- `customer_id` – ID of the customer.
- `event_start` / `event_end` – start and end times of the DR event (must be 2–6 hours apart).
- `contract_capacity_kw` – the participant’s contract capacity (optional).  If provided, it caps the CBL as in the baseline calculation.
 - `committed_capacity_kw` – the participant’s **committed reduction capacity** (optional).  If provided, the endpoint will compute an **execution rate** (actual reduction ÷ committed capacity) and a **reduction ratio** following the day‑select reward table (0, 0.8, 1.0, 1.2).

The response includes the baseline (`cbl_kw`), the actual average demand during the event, the actual reduction, and—if `committed_capacity_kw` is provided—the **execution rate** and **reduction ratio**.  It also returns the list of baseline source days and a `detail` object containing intermediate values such as `cbl1_kw`, `af_kw`, `hist_adjust_avg_kw`, `today_adjust_avg_kw`, and, when applicable, `execution_rate` and `reduction_ratio`.

### Batch production time tariff (批次生產時間電價)

For participants opting into the batch production time tariff, the event window is fixed to **15:30–21:30** (`batch_time_tariff: true`). Two ready-to-use samples are included:

```bash
curl -X POST http://localhost:18000/dr/day-select/cbl \
  -H "Content-Type: application/json" \
  --data @samples/day_select_batch_cbl_correct.json

curl -X POST http://localhost:18000/dr/day-select/reward \
  -H "Content-Type: application/json" \
  --data @samples/day_select_batch_reward_correct.json
```

Both samples contain complete 15-minute data for the required 15:30–21:30 window.

## Demonstration Dataset

`sample_meter_data.json` contains 15-minute data for `C001` covering 20 baseline weekdays plus the event day (event window 16:00–22:00, adjustment window 22:00–24:00). Use it directly—no batch upload endpoint is needed.

Quick test:

```bash
uvicorn main:app --reload

jq '{
  customer_id: "C001",
  event_start: "2025-07-01T16:00:00+08:00",
  event_end: "2025-07-01T22:00:00+08:00",
  contract_capacity_kw: 120,
  committed_capacity_kw: 100,
  records: .records
}' sample_meter_data.json > day_select_reward.json

curl -X POST http://localhost:18000/dr/day-select/reward \
     -H "Content-Type: application/json" \
     --data @day_select_reward.json
```


### `POST /dr/day-select/reward`

Compute the **daily electricity‑fee deduction (回饋金)** for a given DR event.  This endpoint builds upon the CBL calculation and applies Taipower’s reward formula for the day‑select plan:

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
- `event_start` / `event_end` – start and end times of the DR event (must be 2, 4 or 6 hours apart)
- `records` – 15-minute meter records (same coverage as `/dr/day-select/cbl`)
- `contract_capacity_kw` – the customer’s contract capacity (CBL2) used in the CBL calculation
- `committed_capacity_kw` – the committed reduction capacity (約定抑低契約容量) used for the reward formula
- Optional: `assumed_af_kw` – provide an assumed 22:00–24:00 average if calculating before event-day data is available (used for AF).

Example (using the sample payload built above):

```bash
curl -X POST http://localhost:18000/dr/day-select/reward \
     -H "Content-Type: application/json" \
     --data @day_select_reward.json
```

Sample response (numbers will vary with your data):

```json
{
  "customer_id": "C001",
  "event_start": "2025-07-01T16:00:00+08:00",
  "event_end": "2025-07-01T22:00:00+08:00",
  "committed_capacity_kw": 100.0,
  "cbl_kw": 99.91,
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
    "reward_ntd": 0.0
  }
}
```

## Variable Definitions

The API responses include several fields and intermediate values.  Here is a concise definition of each key variable used in the CBL and reward calculations:

- **`CBL1`** – The 20‑day average demand across the DR event’s time window【106788555196366†L136-L143】.
- **`AF` (Load‑Adjustment Factor)** – The difference between the event‑day average demand in the 22:00–24:00 window and the 20‑day historical average of the same window【106788555196366†L141-L147】; if the difference is negative, it is treated as zero【106788555196366†L141-L147】.
- **`CBL2`** – The participant’s **contract capacity** (經常契約容量).  The final baseline will not exceed this value【164418267621156†L24-L35】.
- **`cbl_kw` (Final CBL)** – The **minimum** of `CBL1 + AF` and `CBL2`【164418267621156†L24-L35】.  This is the baseline used to determine the actual reduction.
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

The current implementation focuses solely on the 日選時段型 CBL calculation.  In a production system you may wish to extend the server with:

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
4. **Execution rate** – The ratio of the actual reduction to the participant’s **contract capacity**.  It is rounded to one decimal place and capped at **1.0 (100%)**【574061540680747†L258-L272】.

### Fee Reduction and Penalty Rules

The monthly fee adjustment consists of a **basic fee reduction** and a **flow fee reduction**, minus any **extra charges**:

- **Basic fee reduction** – Calculated from the contract capacity and a basic fee rate (NTD per kW per month).  The rate depends on the notification advance time (93 for 30 min, 84 for 60 min, 78 for 120 min)【574061540680747†L240-L253】.  A reduction ratio is applied based on the **average execution rate** across all events in the month:
  - Average execution < 70 % → ratio = 0
  - 70 % ≤ average < 80 % → ratio = 0.6
  - 80 % ≤ average < 95 % → ratio = 0.8
  - Average ≥ 95 % → ratio = 1.0【574061540680747†L258-L272】
- **Flow fee reduction** – For each event, if the execution rate ≥ 70 %, the participant receives a reduction equal to **actual reduction × event duration × flow fee rate** (default flow fee rate is 12 NTD per kWh)【574061540680747†L282-L286】.  Otherwise, the flow reduction is zero.
- **Extra charge** – If an event’s execution rate < 60 %, the participant is charged: 

  \[(1 − \text{execution_rate}) × \text{contract_capacity_kw} × \text{event_duration_hours} × \text{flow_fee_rate} × 2\]

  This penalty doubles the flow fee rate and applies to the portion of the committed capacity that was not met【574061540680747†L288-L291】.
- **No events** – If no events are notified in a month, the basic fee reduction defaults to **contract_capacity × basic_fee_rate**【574061540680747†L295-L297】.

### Endpoints

Two additional endpoints implement these rules for the guaranteed response plan:

#### `POST /dr/guaranteed/cbl`

Compute the baseline (two‑hour pre‑notification average) for a single guaranteed response event.  Use this endpoint **before** dispatch to determine the participant’s typical load without the need for actual event data.

Request fields:

- `customer_id` – ID of the participant.
- `event_start` – scheduled start time of the event (ISO 8601).
- `notification_minutes_before` – minutes of advance notice (30, 60 or 120).
- `contract_capacity_kw` – the participant’s committed reduction capacity (kW).

The response returns the baseline kW and the time window used for the calculation.

#### `POST /dr/guaranteed/reduction`

Compute the baseline and **actual reduction** for a single guaranteed response event.  This endpoint should be used **after** the event has occurred.  The request body must include:

- `customer_id` – ID of the participant.
- `event_start` / `event_end` – start and end timestamps of the event (ISO 8601).  The difference between them must be 2, 3 or 4 hours【574061540680747†L208-L238】.
- `notification_minutes_before` – minutes of advance notice (30, 60 or 120).
- `contract_capacity_kw` – the participant’s committed reduction capacity (kW).
- Optional: `basic_fee_rate` and `flow_fee_rate` – override the default rates.

The response returns the baseline kW, the actual average demand and reduction, the execution rate, and the flow fee reduction or extra charge for that event.

#### `POST /dr/guaranteed/reward`

Compute the **monthly electricity‑fee adjustment** for a guaranteed response participant.  The request body must include:

- `customer_id` – ID of the participant.
- `notification_minutes_before` – the standard advance notice for the month (30, 60 or 120).
- `contract_capacity_kw` – the participant’s contract capacity (kW).
- `events` – a list of objects describing each event in the month (each object must include `event_start`, `event_end`, and optionally `basic_fee_rate` and `flow_fee_rate`).
- Optional: `basic_fee_rate` and `flow_fee_rate` – override the default rates for all events.

The endpoint calculates, for each event, the baseline, reduction, execution rate, flow reduction and extra charge.  It then computes the average execution rate for the month, applies the appropriate reduction ratio to the basic fee, sums the flow reductions and extra charges, and returns the net reward.

### Variables for the Guaranteed Response Plan

- **`baseline_kw`** – The average demand during the 2‑hour window preceding the notification time【574061540680747†L208-L238】.
- **`actual_avg_kw`** – The average demand during the event window.
- **`actual_reduction_kw`** – `max(baseline_kw − actual_avg_kw, 0)`【574061540680747†L235-L238】.
- **`execution_rate`** – `(actual_reduction_kw / contract_capacity_kw)`, rounded to one decimal place and capped at 1.0 (100%)【574061540680747†L258-L272】.
- **`event_duration_hours`** – Length of the event in hours (2, 3 or 4).
- **`flow_reduction_amount`** – For each event, if `execution_rate ≥ 0.7`, equals `actual_reduction_kw × event_duration_hours × flow_fee_rate`; otherwise zero【574061540680747†L282-L286】.
- **`extra_charge_amount`** – For each event, if `execution_rate < 0.6`, equals `(1 − execution_rate) × contract_capacity_kw × event_duration_hours × flow_fee_rate × 2`; otherwise zero【574061540680747†L288-L291】.
- **`average_execution_rate`** – The average of all event execution rates across the month.
- **`reduction_ratio`** – Multiplier for the basic fee reduction based on the average execution rate (0, 0.6, 0.8 or 1.0)【574061540680747†L258-L272】.
- **`basic_fee_rate`** – The monthly fee rate per kW, determined by the notification advance time (93, 84 or 78 NTD/kW)【574061540680747†L240-L253】.
- **`flow_fee_rate`** – The per‑kWh flow fee rate (default 12 NTD/kWh)【574061540680747†L240-L253】.
- **`basic_reduction_amount`** – `contract_capacity_kw × basic_fee_rate × reduction_ratio` (or `contract_capacity_kw × basic_fee_rate` if no events occurred)【574061540680747†L295-L297】.
- **`flow_reduction_total_amount`** – Sum of `flow_reduction_amount` across all events in the month.
- **`extra_charge_total_amount`** – Sum of `extra_charge_amount` across all events.
- **`net_reward_amount`** – `basic_reduction_amount + flow_reduction_total_amount − extra_charge_total_amount`.

## Samples

Sample payloads live in `samples/`:
- Day-select CBL pre-event: `samples/day_select_cbl_correct.json` (valid; uses `assumed_af_kw`, baseline-only records) and `samples/day_select_cbl_wrong.json` (invalid: missing a baseline slot).
- Day-select reward/reduction post-event: `samples/day_select_reward_correct.json` (valid) and `samples/day_select_reward_wrong.json` (invalid: missing an event-window slot).
- Guaranteed CBL pre-event: `samples/guaranteed_cbl_correct.json` (valid) and `samples/guaranteed_cbl_wrong.json` (invalid: misaligned timestamp).
- Guaranteed reward/reduction post-event: `samples/guaranteed_reward_correct.json` (valid) and `samples/guaranteed_reward_wrong.json` (invalid: missing an event-window slot).

Quick calls:

```bash
# Day-select CBL (pre-event, assumed adjust)
curl -X POST http://localhost:18000/dr/day-select/cbl \
  -H "Content-Type: application/json" \
  --data @samples/day_select_cbl_correct.json

# Day-select reward (post-event)
curl -X POST http://localhost:18000/dr/day-select/reward \
  -H "Content-Type: application/json" \
  --data @samples/day_select_reward_correct.json

# Guaranteed CBL (pre-event)
curl -X POST http://localhost:18000/dr/guaranteed/cbl \
  -H "Content-Type: application/json" \
  --data @samples/guaranteed_cbl_correct.json

# Guaranteed reward (post-event)
curl -X POST http://localhost:18000/dr/guaranteed/reward \
  -H "Content-Type: application/json" \
  --data @samples/guaranteed_reward_correct.json
```

## Sample Calls and Expected Results

- `samples/day_select_cbl_correct.json` → `POST /dr/day-select/cbl`: 200 OK. `cbl_kw` ~100 (AF ≈ 0 because assumed_af_kw=95 is below hist adjust). Baseline dates list returned.
- `samples/day_select_cbl_wrong.json` → `POST /dr/day-select/cbl`: 400 with message like `缺少 ... 15 分鐘區間` (baseline window gap).
- `samples/day_select_reward_correct.json` → `POST /dr/day-select/reward`: 200 OK. `cbl_kw` ~100; event avg < baseline so positive `actual_reduction_kw`; execution_rate based on committed=100.
- `samples/day_select_reward_wrong.json` → `POST /dr/day-select/reward`: 400 with message like `事件日 ... 缺少 ... 15 分鐘區間` (event window gap).
- `samples/guaranteed_cbl_correct.json` → `POST /dr/guaranteed/cbl`: 200 OK. `baseline_kw` ~100 (average of 08:00–10:00).
- `samples/guaranteed_cbl_wrong.json` → `POST /dr/guaranteed/cbl`: 400 with message like `時間戳未對齊 15 分鐘`.
- `samples/guaranteed_reward_correct.json` → `POST /dr/guaranteed/reward`: 200 OK. `baseline_kw` ~100, event avg ~30 → reduction ~70, execution_rate ~0.8 on committed=90; flow reduction positive, no penalty.
- `samples/guaranteed_reward_wrong.json` → `POST /dr/guaranteed/reward`: 400 with message like `缺少 ... 15 分鐘區間` (event window gap).
