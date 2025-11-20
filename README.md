# DR_onsite

Onsite Demand Response Module.

## Demand Response API

The `app.py` module exposes a FastAPI application with a `/dayDR` endpoint. The
endpoint validates a DR call against contractual and scheduling rules and
returns a calculated Criteria Base Load (CBL) when the request is accepted.

### Request payload

```json
{
  "measure": "dayDR",
  "capacityDR": 25,
  "timespanDR": {
    "start": "2024-06-12T08:00:00Z",
    "end": "2024-06-12T10:00:00Z"
  },
  "timezone": "Asia/Taipei"
}
```

### Behavior overview

- Reads `contract_value` from Redis key `setting_json` and ignores calls when the
  value is not greater than 100.
- Verifies the DR window is Monday–Friday between May 1 and October 31, and that
  the local timespan matches one of: 18:00–20:00, 16:00–20:00, or 16:00–22:00.
- Requires `capacityDR` to exceed 20 kW.
- Requires `measure` to be `dayDR`.
- When conditions pass, reads the last 20 days of 15-minute load samples from
  Redis key `load_profile:15m` and returns the average of each day's minimum
  load within the requested timespan as the CBL.

### Running locally

```bash
uvicorn app:app --reload
```

Set `REDIS_URL` if your Redis instance is not on `localhost:6379`.

### Running with Docker Compose

The included `docker-compose.yml` starts both the API service and a Redis
instance with the expected connection string.

```bash
docker compose up --build
```

This exposes the API on http://localhost:8000 with Redis reachable at the
default `redis://redis:6379/0` URL configured for the app container.

### Quick demo

1) Start the stack:

```bash
docker compose up --build -d
```

2) Seed Redis with a contract value and sample 15-minute load profile for the
last 20 days (defaults to `redis://localhost:6379/0` and UTC; override
`--timezone` to match your local window rules):

```bash
python scripts/seed_demo.py --timezone Asia/Taipei
```

3) Submit a DR call using curl. The window below aligns with the seeded profile
and accepted DR windows (16:00–20:00 local):

```bash
curl -X POST http://localhost:8000/dayDR \
  -H "Content-Type: application/json" \
  -d '{
        "measure": "dayDR",
        "capacityDR": 25,
        "timespanDR": {
          "start": "2024-06-12T08:00:00Z",
          "end": "2024-06-12T12:00:00Z"
        },
        "timezone": "Asia/Taipei"
      }'
```

Expected response (CBL derived from the seeded trough between 18:00–20:00 each
day):

```json
{
  "accepted": true,
  "reason": null,
  "cbl": 70.0
}
```
