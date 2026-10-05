# malaysia-flights-pipeline

A daily data pipeline that collects flight arrivals and departures at four Malaysian airports from the [OpenSky Network](https://opensky-network.org/) API and loads them into PostgreSQL. The airports are Kuala Lumpur International (KLIA, `WMKK`), Sultan Abdul Aziz Shah in Subang (`WMSA`), Penang International (`WMKP`) and Kota Kinabalu International (`WBKK`). dbt models to clean and model the data will follow.

## Status

- **Ingestion: complete.** Daily runs and date-range backfills, with idempotent loads, retries and a per-call audit log.
- **dbt models: in progress.** Nothing is transformed yet; the data sits in the `raw` schema exactly as OpenSky returned it.

## Architecture

```
OpenSky REST API  ──►  Python ingestion  ──►  PostgreSQL: raw schema  ──►  dbt models (planned)
  /flights/arrival       (ingestion/)          raw.flights                  staging → marts
  /flights/departure                           raw.api_runs
```

Each run makes one API call per airport, direction and day: 4 airports × 2 directions = 8 calls per day.

## Tech stack

- Python 3.13, managed with [uv](https://docs.astral.sh/uv/)
- `requests` for the API, with `urllib3` retries
- `psycopg` 3 for PostgreSQL
- PostgreSQL 16 in Docker
- dbt (planned)

## Quick start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A free [OpenSky Network](https://opensky-network.org/) account, with an API client created on your account page (this gives you a client ID and secret)

### 1. Clone and configure

```bash
git clone https://github.com/siti-zu/malaysia-flights-pipeline.git
cd malaysia-flights-pipeline
cp .env.example .env
```

Fill in `.env`. The database values are used both to create the Postgres container and to connect to it, so you can choose any user, password and database name:

```bash
DB_HOST=localhost
DB_PORT=5433          # any free port; 5433 avoids clashing with a local Postgres on 5432
DB_NAME=flights
DB_USER=flights
DB_PASSWORD=change-me

CLIENT_ID=your-opensky-client-id
CLIENT_SECRET=your-opensky-client-secret
```

### 2. Start Postgres

```bash
docker compose up -d
```

On first start, the scripts in [sql/](sql/) create the `raw` schema and tables.

### 3. Create the environment

```bash
uv venv --python 3.13
uv pip install -r requirements.txt
```

### 4. Run it

```bash
# Yesterday (UTC), the default daily run
uv run python -m ingestion.main

# A single date
uv run python -m ingestion.main --date 2026-09-15

# An inclusive date range (--end defaults to yesterday)
uv run python -m ingestion.main --start 2026-09-01 --end 2026-09-07

# The last 7 days, ending yesterday
uv run python -m ingestion.main --days 7
```

Dates must be yesterday or earlier: OpenSky processes each day's flights in a nightly batch. Run `--help` for all options.

## How it works

### ELT: raw data first, transformations later

Each flight is stored as the untouched JSON object OpenSky returned, in a `JSONB` column. Cleaning, typing and modelling will happen later in SQL with dbt. If a transformation turns out to be wrong, it can be fixed and re-run against the raw data without calling the API again, which matters when every call costs credits.

### Idempotent loads

Data is loaded one airport, direction and day at a time. The loader deletes that slice and inserts the new rows in a single transaction, so either both happen or neither does. Re-running any day, or overlapping a backfill with days already loaded, never creates duplicates.

### Failure handling

- Every API call is logged to `raw.api_runs` with its status code, row count, remaining credits and any error message.
- One failed call doesn't stop the others. If a single airport fails, the rest of the day still loads, and the run exits with code 1 so a scheduler can flag it.
- `401` (bad credentials) and `429` (out of credits) stop the whole run straight away, because every remaining call would fail the same way and still be logged as a failure.
- If the database can't be reached, the run stops with a clear message instead of carrying on without an audit trail.

<!-- Screenshot: backfill stopping cleanly at the credit limit -->

### Retries

Temporary server errors (`500`, `502`, `503`, `504`) and connection errors are retried up to 3 times with exponential backoff, before the call is counted as failed.

### Credit budget

OpenSky charges 30 credits per call for these endpoints, so one day of data costs 8 × 30 = **240 credits**. The remaining balance is recorded on every row of `raw.api_runs`.

Backfills that hit the daily credit limit stop cleanly on the `429`. To resume, check `raw.api_runs` for the last day that completed and re-run with `--start` set to the day after it. Because loads are idempotent, starting from a day that was already partly loaded is safe.

### Run IDs

Every run gets a UUID, written to every row it creates in both `raw.flights` and `raw.api_runs`. Any row can be traced back to the run that loaded it, and everything that happened in one run is a single `WHERE run_id = ...` query.

## Data model (so far)

**`raw.flights`**: one row per flight returned by the API. It stores the airport and direction queried, the UTC day requested, the run ID, a load timestamp, and the flight itself as untouched JSON in `payload`.

**`raw.api_runs`**: one row per API call, successful or not. It records the HTTP status, rows returned, credits left and any error message, and is used for monitoring, debugging and resuming backfills.

The full schema is in [sql/init.sql](sql/init.sql).

## Data notes

Observations from the raw data, based on 12,639 flights across 14 days loaded so far (September–October 2026):

- **Callsigns are padded to 8 characters with trailing spaces**, for example `"MAS066  "`. They need trimming before joins or display.
- **The other airport is often unknown.** 52% of arrivals have a null `estDepartureAirport`, and 42% of departures have a null `estArrivalAirport`. This happens when OpenSky didn't track the aircraft near the other end of the flight.
- **The same aircraft appears many times a day.** `icao24` identifies the aircraft, not the flight. On a given day, 53% of aircraft appear more than once: they fly several legs, appear as both an arrival and a departure at the same airport, or fly between two of the four airports. A flight key needs `icao24` plus timing, not `icao24` alone.
- **`firstSeen` and `lastSeen` are not take-off and landing times.** They are the Unix timestamps (seconds, UTC) at which OpenSky's receivers first and last picked up the aircraft. They're close to the real times, but they depend on receiver coverage.

## Known limitations

- **Resuming a backfill is manual.** The pipeline doesn't yet read `raw.api_runs` to skip days that already loaded.
- **No automated tests yet.**

## Roadmap

- [ ] dbt staging models: trim callsigns, convert Unix times to timestamps, deduplicate flights
- [ ] dbt marts: daily traffic by airport, airline and route
- [ ] Tests (pytest for ingestion, dbt tests for models) and CI with GitHub Actions
- [ ] Orchestration with Airflow, for daily scheduling and automatic backfill resume
- [ ] Move to a cloud warehouse

## Data credits

Flight data is provided by [The OpenSky Network](https://opensky-network.org/). If you use this data in research, OpenSky asks that you cite:

> Matthias Schäfer, Martin Strohmeier, Vincent Lenders, Ivan Martinovic and Matthias Wilhelm. "Bringing Up OpenSky: A Large-scale ADS-B Sensor Network for Research". In *Proceedings of the 13th IEEE/ACM International Symposium on Information Processing in Sensor Networks (IPSN)*, pages 83–94, April 2014.
