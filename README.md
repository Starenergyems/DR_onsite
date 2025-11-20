# DR API Server – 日選時段型 CBL

This repository contains a reference implementation of a **Demand Response (DR) API server** written in Python using FastAPI.  The goal of the service is to compute the **Customer Baseline Load (CBL)** for participants in the **日選時段型 (day‑select time‑slot)** DR program as defined by Taipower.  A CBL represents the participant’s typical load during a DR event and is used to determine the actual load reduction and corresponding reward.

## Background

According to Taipower’s official regulations, the baseline for the 日選時段型 program is calculated by averaging the participant’s demand during the same time slot across the **20 most recent qualifying days** (non‑event days, non‑off‑peak days, and weekdays)【106788555196366†L136-L143】.  This average is then **adjusted by a load‑adjustment factor**.  The load‑adjustment factor is defined as the difference between

1. the participant’s average demand from **22:00 to 24:00 (afternoon 10 to 12)** on the event day, and
2. the average demand in the same 22:00‑24:00 window across the previous 20 qualifying days【106788555196366†L141-L147】.

If this difference is negative it is treated as zero【106788555196366†L141-L147】.  Under the latest guidelines, the **final CBL (基準用電容量)** should take the **smaller** of `CBL1 + AF` and the participant’s **contract capacity (CBL2)**【164418267621156†L24-L35】.  Here `CBL1` is the 20‑day average over the event window, and `AF` is the load‑adjustment factor described above.  The implementation in `main.py` follows this logic.

## Features

- **FastAPI server** with clear, self‑documenting endpoints.
- **In‑memory storage** for 15‑minute metering records (kW).  In production this can be replaced by a database such as PostgreSQL or TimescaleDB.
- **CBL computation** for the 日選時段型 DR plan, including handling of cross‑day intervals (22:00–24:00) for the load‑adjustment factor.
- **Sample dataset** and step‑by‑step instructions to demonstrate uploading meter data and retrieving the computed CBL.

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

### `POST /meter-data/batch`

Upload a batch of 15‑minute metering records.  The request body must be JSON with a `records` field containing a list of objects:

- `customer_id` – identifier for the customer (string)
- `timestamp`  – ISO 8601 timestamp with time zone (e.g. `"2025-06-10T16:00:00+08:00"`)
- `kw`         – average demand during the 15‑minute interval (float, ≥ 0)

Example request:

```bash
curl -X POST http://localhost:18000/meter-data/batch \
     -H "Content-Type: application/json" \
     --data @sample_meter_data.json
```

### `POST /dr/day-select/cbl`

Compute the CBL for a given DR event.  The request body must include:

- `customer_id` – ID of the customer
- `event_start` – start time of the DR event (ISO 8601 with time zone)
- `event_end`   – end time of the DR event (must be later than the start time)

**Additional field**: `contract_capacity_kw` – the participant’s contract capacity in kW (CBL2).  If provided, the final CBL will be the smaller of `CBL1 + AF` and this contract capacity【164418267621156†L24-L35】.

When called, the endpoint will:

1. Verify that the event lies within the valid program window (5 May – 31 Oct)【106788555196366†L120-L128】.
2. Locate the 20 most recent qualifying days prior to the event (excluding weekends, off‑peak days and previous DR days)
3. Compute the 20‑day average demand over the event’s time window【106788555196366†L136-L143】.
4. Compute the load‑adjustment factor using the 22:00–24:00 window【106788555196366†L141-L147】.
5. Return a JSON response containing the baseline kW, the list of dates used as baseline sources and intermediate calculation details.

Example request:

```bash
curl -X POST http://localhost:18000/dr/day-select/cbl \
     -H "Content-Type: application/json" \
     -d '{
         "customer_id": "C001",
         "event_start": "2025-07-01T16:00:00+08:00",
         "event_end":   "2025-07-01T22:00:00+08:00",
         "contract_capacity_kw": 120
     }'
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

## Demonstration Dataset

To help you try out the API quickly, a **sample dataset** is included in this repository: `sample_meter_data.json`.  It contains 15‑minute metering records for one customer (`C001`) covering the 20 baseline days prior to a sample event on 1 July 2025 (16:00–22:00) as well as the event day itself.  The baseline values are around 100 kW during both the event window and the 22:00–24:00 window, while the event day is slightly lower to illustrate a positive reduction.

Steps to run the demo:

1. Start the server:

   ```bash
   uvicorn main:app --reload
   ```

2. Upload the sample meter data:

   ```bash
   curl -X POST http://localhost:18000/meter-data/batch \
        -H "Content-Type: application/json" \
        --data @sample_meter_data.json
   ```

3. Request the CBL for the event (and provide the contract capacity):

   ```bash
   curl -X POST http://localhost:18000/dr/day-select/cbl \
        -H "Content-Type: application/json" \
        -d '{
          "customer_id": "C001",
          "event_start": "2025-07-01T16:00:00+08:00",
          "event_end":   "2025-07-01T22:00:00+08:00",
          "contract_capacity_kw": 120
        }'
   ```

The response will include the computed `baseline_kw` along with intermediate details showing the baseline event‑window average, the historical adjustment average and the load‑adjustment factor.

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
- `contract_capacity_kw` – the customer’s contract capacity (CBL2) used in the CBL calculation
- `committed_capacity_kw` – the committed reduction capacity (約定抑低契約容量) used for the reward formula

Example request:

```bash
curl -X POST http://localhost:18000/dr/day-select/reward \
     -H "Content-Type: application/json" \
     -d '{
       "customer_id": "C001",
       "event_start": "2025-07-01T16:00:00+08:00",
       "event_end":   "2025-07-01T22:00:00+08:00",
       "contract_capacity_kw": 120,
       "committed_capacity_kw": 100
     }'
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
