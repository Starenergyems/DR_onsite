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

## Extending the Server

The current implementation focuses solely on the 日選時段型 CBL calculation.  In a production system you may wish to extend the server with:

- **Persistent storage** (e.g. TimescaleDB or PostgreSQL) for meter data.
- **Additional DR plans** such as the 月選8日型 or 即時性 adjustments【106788555196366†L134-L147】.
- **Electricity‑fee deduction calculations** based on the calculated CBL and participant’s contract capacity【106788555196366†L154-L182】.
- **User authentication** and multi‑tenant support for different customers.

By building on this foundation, you can create a complete DR management platform that complies with Taipower’s regulations and provides participants with transparent and auditable baseline calculations.
