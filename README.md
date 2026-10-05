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

The seed scripts live in [scripts/](scripts/) and are run as modules from the repo root, like the ingestion. That way `scripts.build_aircraft_seed` can import `ingestion` without changing `sys.path`.

**`airlines` seed**: a dbt seed at [malaysia_flights_dbt/seeds/airlines.csv](malaysia_flights_dbt/seeds/airlines.csv) that maps 3-letter ICAO airline codes (`airline_code`) to names (`airline_name`), so airlines can be identified from the first three letters of a callsign. It's built from OpenFlights' `airlines.dat`. Some ICAO codes appear more than once in that file, because codes from defunct airlines get reused, so the seed keeps one name per code and prefers the active airline. To regenerate it:

```bash
python -m scripts.build_airlines_seed
```

**`airports` seed**: a dbt seed at [malaysia_flights_dbt/seeds/airports.csv](malaysia_flights_dbt/seeds/airports.csv) that maps 4-letter ICAO airport codes (`airport_code`) to `airport_name`, `city`, `country_code` (ISO 3166-1 alpha-2), `latitude` and `longitude`. It's built from OurAirports' `airports.csv`. It covers the whole world, because flights go to destinations everywhere, but keeps only `large_airport` and `medium_airport` types to stay small (about 5,000 rows). If an airport has no `icao_code`, its `ident` is used as long as it's 4 letters. To regenerate it:

```bash
python -m scripts.build_airports_seed
```

**`aircraft` seed**: a dbt seed at [malaysia_flights_dbt/seeds/aircraft.csv](malaysia_flights_dbt/seeds/aircraft.csv) that maps `icao24` to `registration`, `manufacturer`, `model`, `typecode`, `operator` and `operator_icao`. It's built from OpenSky's aircraft database (the `aircraft-database-complete-2025-08.csv` snapshot). That snapshot is pinned on purpose so the seed is reproducible; newer snapshots exist, and moving to one should be a deliberate change. The full file is over 100 MB, so the script keeps only the aircraft that appear in `raw.flights`. It needs the database to be running. To regenerate it:

```bash
python -m scripts.build_aircraft_seed
```

> **This seed goes stale after every load.** Unlike the other two seeds, it depends on what's in `raw.flights`. Aircraft loaded by a new daily run or backfill won't have a registration, model or operator until you re-run the script and `dbt seed`. Until then they still appear in `stg_flights`, just without details, as long as models join to `stg_aircraft` with a left join.

## Data notes

Observations from the raw data, based on 12,639 flights across 14 days loaded so far (September–October 2026):

- **Callsigns are padded to 8 characters with trailing spaces**, for example `"MAS066  "`. They need trimming before joins or display.
- **The other airport is often unknown.** 52% of arrivals have a null `estDepartureAirport`, and 42% of departures have a null `estArrivalAirport`. This happens when OpenSky didn't track the aircraft near the other end of the flight.
- **The same aircraft appears many times a day.** `icao24` identifies the aircraft, not the flight. On a given day, 53% of aircraft appear more than once: they fly several legs, appear as both an arrival and a departure at the same airport, or fly between two of the four airports. A flight key needs `icao24` plus timing, not `icao24` alone.
- **The aircraft database is incomplete.** Of the 1,394 aircraft seen so far, 114 aren't in OpenSky's aircraft database. Of the 1,280 that are, `typecode` is filled for almost all of them, but `operator` is blank for 76% and `operator_icao` for 41%. For the airline, the callsign prefix joined to the `airlines` seed is the more reliable source.
- **`firstSeen` and `lastSeen` are not take-off and landing times.** They are the Unix timestamps (seconds, UTC) at which OpenSky's receivers first and last picked up the aircraft. They're close to the real times, but they depend on receiver coverage.

## Known limitations

- **Resuming a backfill is manual.** The pipeline doesn't yet read `raw.api_runs` to skip days that already loaded.
- **The ingestion code has no automated tests.** dbt tests cover the staging models, but there are no pytest tests yet.
- **17 aircraft have an operator code that isn't in the airlines seed**, for example `RMY` (Royal Malaysian Air Force). The relationship test on `stg_aircraft.operator_icao` is set to warn rather than fail for this reason.

## Roadmap

- [ ] dbt staging models: trim callsigns, convert Unix times to timestamps, deduplicate flights
- [ ] dbt marts: daily traffic by airport, airline and route
- [ ] pytest tests for ingestion, and CI with GitHub Actions (dbt tests for the staging models are done)
- [ ] Orchestration with Airflow, for daily scheduling and automatic backfill resume
- [ ] Move to a cloud warehouse

## Data credits

Flight data is provided by [The OpenSky Network](https://opensky-network.org/). If you use this data in research, OpenSky asks that you cite:

> Matthias Schäfer, Martin Strohmeier, Vincent Lenders, Ivan Martinovic and Matthias Wilhelm. "Bringing Up OpenSky: A Large-scale ADS-B Sensor Network for Research". In *Proceedings of the 13th IEEE/ACM International Symposium on Information Processing in Sensor Networks (IPSN)*, pages 83–94, April 2014.

Reference data for the dbt seeds comes from three sources, each with its own licence:

- **Aircraft details** (`aircraft` seed) come from the [OpenSky Network aircraft database](https://opensky-network.org/datasets/#metadata/), under the same OpenSky [terms of use](https://opensky-network.org/about/terms-of-use) as the flight data. Those terms allow non-profit research and education; commercial use needs OpenSky's written permission.
- **Airline names** (`airlines` seed) come from [OpenFlights](https://openflights.org/data.php), made available under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/1-0/), with individual contents under the [Database Contents License](https://opendatacommons.org/licenses/dbcl/1-0/). The ODbL requires attribution, and derived databases shared publicly, such as `airlines.csv`, must stay under the ODbL.
- **Airport data** (`airports` seed) comes from [OurAirports](https://ourairports.com/data/), which releases its data into the public domain. No attribution is required, but it's credited here anyway.


dbt notes
- first_seen has null (id 6894 in raw.flights)
