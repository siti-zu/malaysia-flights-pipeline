[![CI](https://github.com/siti-zu/malaysia-flights-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/siti-zu/malaysia-flights-pipeline/actions/workflows/ci.yml)

# malaysia-flights-pipeline

A daily data pipeline that collects flight arrivals and departures at four Malaysian airports from the [OpenSky Network](https://opensky-network.org/) API and loads them into PostgreSQL. The airports are Kuala Lumpur International (KLIA, `WMKK`), Sultan Abdul Aziz Shah in Subang (`WMSA`), Penang International (`WMKP`) and Kota Kinabalu International (`WBKK`). dbt models to clean and model the data will follow.

## Status

- **Ingestion: complete.** Daily runs and date-range backfills, with idempotent loads, retries and a per-call audit log.
- **dbt models: in progress.** Staging models, a deduplicated `fct_flights`, three dimensions (airport, airline, aircraft) and three reporting marts (top routes, busiest hours, flights per airline) are built and tested. See [Results](#results).

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
- GitHub Actions for CI
- dbt Core with the Postgres adapter, plus the [dbt_utils](https://hub.getdbt.com/dbt-labs/dbt_utils/latest/) package

## Quick start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- `make` (already on macOS and most Linux systems)
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
# Any free port; 5433 avoids clashing with a local Postgres on 5432
DB_PORT=5433
DB_NAME=flights
DB_USER=flights
DB_PASSWORD=change-me

CLIENT_ID=your-opensky-client-id
CLIENT_SECRET=your-opensky-client-secret
```

### 2. Set up and start Postgres

```bash
make install
make up
```

On first start, the scripts in [sql/](sql/) create the `raw` schema and tables.

### 3. Run it

```bash
make ingest                                      # yesterday (UTC), the default daily run
make ingest DATE=2026-09-15                      # a single date
make backfill START=2026-09-01 END=2026-09-07    # an inclusive range; END defaults to yesterday
make transform                                   # load the seeds, build every dbt model and run every test
```

Dates must be yesterday or earlier: OpenSky processes each day's flights in a nightly batch.

Run `make help` to list every command. `make down` stops Postgres and keeps the data. For options without a `make` command, such as the last N days, call the module directly: `uv run python -m ingestion.main --days 7`. Run it with `--help` for all options.

## How it works

### ELT: raw data first, transformations later

Each flight is stored as the untouched JSON object OpenSky returned, in a `JSONB` column. Cleaning, typing and modelling will happen later in SQL with dbt. If a transformation turns out to be wrong, it can be fixed and re-run against the raw data without calling the API again, which matters when every call costs credits.

### Idempotent loads

Data is loaded one airport, direction and day at a time. The loader deletes that slice and inserts the new rows in a single transaction, so either both happen or neither does. Re-running any day, or overlapping a backfill with days already loaded, never creates duplicates.

### Failure handling

- Every API call is logged to `raw.api_runs` with its status code, row count, remaining credits and any error message.
- One failed call doesn't stop the others. If a single airport fails, the rest of the day still loads, and the run exits with code 1 so a scheduler can flag it.
- `401` (bad credentials) and `429` (out of credits) stop the whole run straight away, because every remaining call would fail the same way and still be logged as a failure.
- If the database can't be reached, the run stops with a clear message instead of carrying on without an audit trail, and exits with code 1 even if no API call failed.
- If the API call works but the load fails, the row keeps the API's status code, has an `error_message` and no `row_count`. Rows logged before this was fixed still have a `row_count` (8 rows, all for 2026-10-04, which later re-runs loaded cleanly).

<!-- Screenshot: backfill stopping cleanly at the credit limit -->

### Retries

Temporary server errors (`500`, `502`, `503`, `504`) and connection errors are retried up to 3 times with exponential backoff, before the call is counted as failed.

### Credit budget

OpenSky charges 30 credits per call for these endpoints, so one day of data costs 8 × 30 = **240 credits**. The remaining balance is recorded on every row of `raw.api_runs`.

Backfills that hit the daily credit limit stop cleanly on the `429`. To resume, check `raw.api_runs` for the last day that completed and re-run with `--start` set to the day after it. Because loads are idempotent, starting from a day that was already partly loaded is safe.

### Run IDs

Every run gets a UUID, written to every row it creates in both `raw.flights` and `raw.api_runs`. Any row can be traced back to the run that loaded it, and everything that happened in one run is a single `WHERE run_id = ...` query.

### Checking that runs happened and finished

Two dbt checks read `raw.api_runs` to catch a pipeline that stopped or only partly loaded:

- **Source freshness**: `dbt source freshness` warns if the newest call in `raw.api_runs` (by `run_at`) is more than 26 hours old, which means the daily run has stopped. The limit is 26 hours rather than 24, so a run that starts or finishes a little late doesn't trigger it. It's configured in [_sources.yml](malaysia_flights_dbt/models/staging/_sources.yml).
- **Completeness**: the singular test [assert_every_day_has_8_successful_calls.sql](malaysia_flights_dbt/tests/assert_every_day_has_8_successful_calls.sql) fails for any `query_date` without a successful call for all 4 airports × 2 directions, and lists each such date with the number of successful calls it has. A `404` counts as success, because OpenSky returns it when an airport had no flights that day. A call with an `error_message` doesn't count, because the API can return `200` and the load still fail. A day that failed and was later re-run successfully passes, and a day with no calls at all fails. It runs with `dbt test` and `dbt build`.

```bash
make freshness
cd malaysia_flights_dbt && uv run dbt test --select assert_every_day_has_8_successful_calls
```

### CI

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs on every push to `main` and every pull request, with two jobs:

- **`pytest`** runs the Python tests. It uses dummy environment variables, because `config.py` won't import without them and the tests never use their values.
- **`dbt`** starts a throwaway Postgres, creates the raw tables with [sql/init.sql](sql/init.sql), then runs `dbt deps` and `dbt build`.

The raw tables are empty in CI, because the job doesn't call OpenSky. So `dbt build` proves that the project compiles, every model's SQL runs, the seeds load and tests on the seeds pass, but tests on flight data have no rows to check.

## Data model (so far)

**`raw.flights`**: one row per flight returned by the API. It stores the airport and direction queried, the UTC day requested, the run ID, a load timestamp, and the flight itself as untouched JSON in `payload`.

**`raw.api_runs`**: one row per API call, successful or not. It records the HTTP status, rows returned, credits left and any error message, and is used for monitoring, debugging and resuming backfills.

The full schema is in [sql/init.sql](sql/init.sql).

**Marts** (`analytics` schema, built by dbt as tables): a star schema with `fct_flights` at the centre and three dimensions. Each dimension has one row per key, and its key has `unique` and `not_null` tests.

| Model | Grain | Joins to `fct_flights` on |
| --- | --- | --- |
| `fct_flights` | One row per flight, deduplicated (see [Deduplication rule](#deduplication-rule)) | — |
| `dim_airline` | One row per ICAO airline code | `airline_code` |
| `dim_aircraft` | One row per aircraft seen in the flight data | `icao24` |
| `dim_airport` | One row per airport code: large and medium airports worldwide, plus any airport used in the flight data | `est_departure_airport` or `est_arrival_airport` |

Not every flight has a match, so always join the dimensions with a `LEFT JOIN`. An inner join would drop those flights.

#### Dimension coverage

Each join column in `fct_flights` has a `relationships` test against its dimension, set to `severity: warn`. Gaps are expected, so they're reported on every `dbt build` without failing it, and the warning count is the number of flights that can't be matched. Flights with a null value aren't counted, so each rate is out of the flights where the value is known.

Measured on 50,410 flights from 2026-09-04 to 2026-11-02:

| Join | Flights with a value | Unmatched (warn count) | Matched | Why some don't match |
| --- | ---: | ---: | ---: | --- |
| `airline_code` → `dim_airline` | 49,282 | 121 | 99.8% | The first 3 characters of private, military and other non-airline callsigns aren't airline codes. Before the `airline_overrides` seed was added, 6.3% of flights were unmatched. |
| `icao24` → `dim_aircraft` | 50,410 | 3,977 | 92.1% | 221 of the 2,574 aircraft aren't in OpenSky's aircraft database. Aircraft first seen after the seed was last rebuilt also go unmatched until it's rebuilt again (see the `aircraft` seed note above). |
| `est_departure_airport` → `dim_airport` | 31,083 | 0 | 100% | Before the airports seed started including every airport used in the flight data, 1.5% were unmatched. |
| `est_arrival_airport` → `dim_airport` | 43,622 | 0 | 100% | Before the same change, 0.3% were unmatched. |

The seed scripts live in [scripts/](scripts/) and are run as modules from the repo root, like the ingestion. That way `scripts.build_aircraft_seed` can import `ingestion` without changing `sys.path`. `make seeds` runs all three.

**`airlines` seed**: a dbt seed at [malaysia_flights_dbt/seeds/airlines.csv](malaysia_flights_dbt/seeds/airlines.csv) that maps 3-letter ICAO airline codes (`airline_code`) to names (`airline_name`), so airlines can be identified from the first three letters of a callsign. It's built from OpenFlights' `airlines.dat`. Some ICAO codes appear more than once in that file, because codes from defunct airlines get reused, so the seed keeps one name per code and prefers the active airline. To regenerate it:

```bash
python -m scripts.build_airlines_seed
```

**`airports` seed**: a dbt seed at [malaysia_flights_dbt/seeds/airports.csv](malaysia_flights_dbt/seeds/airports.csv) that maps 4-letter ICAO airport codes (`airport_code`) to `airport_name`, `city`, `country_code` (ISO 3166-1 alpha-2), `latitude` and `longitude`. It's built from OurAirports' `airports.csv`. It covers the whole world, because flights go to destinations everywhere, and keeps two sets of airports (about 5,000 rows):

- **Every `large_airport` and `medium_airport`** with a 4-letter ICAO code. If an airport has no `icao_code`, its `ident` is used as long as it's 4 letters.
- **Any airport, of any size, whose code appears in `raw.flights`.** This adds small Malaysian airfields such as Kota Belud (`WBKB`) and Sitiawan (`WMBA`), and small foreign ones such as Indian air force stations, without adding thousands of unused airports. A flight's code is matched against OurAirports' `icao_code`, `ident`, `gps_code` and, last, `keywords`. `keywords` holds retired codes that OpenSky still uses, such as `VGZR` for Dhaka's Hazrat Shahjalal International Airport, which is now `VGHS`. Such an airport then appears under both codes, so group by `airport_name` rather than `airport_code` to count it once.

Like the aircraft seed, the second set depends on the data: re-run the script after loading new days, with the database running. To regenerate it:

```bash
python -m scripts.build_airports_seed
```

**`aircraft` seed**: a dbt seed at [malaysia_flights_dbt/seeds/aircraft.csv](malaysia_flights_dbt/seeds/aircraft.csv) that maps `icao24` to `registration`, `manufacturer`, `model`, `typecode`, `operator` and `operator_icao`. It's built from OpenSky's aircraft database (the `aircraft-database-complete-2025-08.csv` snapshot). That snapshot is pinned on purpose so the seed is reproducible; newer snapshots exist, and moving to one should be a deliberate change. The full file is over 100 MB, so the script keeps only the aircraft that appear in `raw.flights`. It needs the database to be running. To regenerate it:

```bash
python -m scripts.build_aircraft_seed
```

> **This seed goes stale after every load.** Like the airports seed, and unlike the airlines one, it depends on what's in `raw.flights`. Aircraft loaded by a new daily run or backfill won't have a registration, model or operator until you re-run the script and `dbt seed`. Until then they still appear in `stg_flights`, just without details, as long as models join to `stg_aircraft` with a left join.

**`airline_overrides` seed**: a hand-maintained seed at [malaysia_flights_dbt/seeds/airline_overrides.csv](malaysia_flights_dbt/seeds/airline_overrides.csv) for airline codes that appear in the flight data but are missing from OpenFlights, such as `RMY` (Raya Airways) and `SJX` (Starlux Airlines). It has the same `airline_code` and `airline_name` columns as `airlines.csv`, plus a `source` column noting where each name was checked. No script builds it; add rows by hand. `stg_airlines` combines it with `airlines.csv`, and an override replaces the OpenFlights name if a code is in both.

## Results

Three reporting marts join `fct_flights` to the dimensions and answer the project's questions. They complete the lineage from `raw.flights` to the answers: `raw.flights → stg_flights → fct_flights → rpt_*`, with the seeds feeding in through the dimensions. Run `make docs` to see the graph.

![dbt lineage graph: the seeds and raw.flights flow through staging models into fct_flights and the three dimensions, which feed the three rpt_ marts; raw.api_runs feeds the completeness test](docs/images/dbt_lineage_graph.png)

Green nodes are the raw sources loaded by the ingestion. On the left are the seeds, then the staging views, then the fact and dimension tables, and on the right the reporting marts. `raw.api_runs` feeds only the completeness test, since it records API calls, not flights.

Each mart has a test on its grain, so a join that fans out fails the build instead of quietly inflating the counts. That can happen if a dimension ever gets two rows for the same key, or if a mart joins on something that isn't unique, such as an airport's name or city: the old and new Dhaka codes (`VGZR` and `VGHS`) are two rows for the same airport. `rpt_top_routes` has a `unique` test on `route`. `rpt_busiest_hours` (one row per airport and hour) and `rpt_flights_per_airline` (one row per airline code) use `dbt_utils.unique_combination_of_columns`. Unlike `unique`, it also catches duplicate rows with a null key.

Figures below cover **50,410 flights from 2026-09-04 to 2026-11-02** (60 days, Malaysia time).

> **KLIA departures are under-counted.** The data has 28,578 arrivals at KLIA (`WMKK`) but only 7,375 departures. A real airport has roughly equal numbers, and the other three airports are close to balanced. OpenSky misses most KLIA departures, so routes *into* KLIA dominate the top routes and KLIA's busiest hours mostly reflect arrivals. Treat both as patterns in OpenSky's coverage, not exact traffic counts.

### Top routes (`rpt_top_routes`)

One row per route where both airports are known, with airport names, cities and countries.

| Rank | Route | From | To | Flights |
| ---: | --- | --- | --- | ---: |
| 1 | WSSS-WMKK | Singapore | Sepang (KLIA) | 2,015 |
| 2 | WIII-WMKK | Jakarta | Sepang (KLIA) | 1,365 |
| 3 | WBKK-WMKK | Kota Kinabalu | Sepang (KLIA) | 1,317 |
| 4 | VHHH-WMKK | Hong Kong | Sepang (KLIA) | 635 |
| 5 | VTBD-WMKK | Bangkok (Don Mueang) | Sepang (KLIA) | 615 |
| 6 | WMKK-WSSS | Sepang (KLIA) | Singapore | 601 |
| 7 | ZGSZ-WMKK | Shenzhen | Sepang (KLIA) | 536 |
| 8 | VTBS-WMKK | Bangkok (Suvarnabhumi) | Sepang (KLIA) | 505 |
| 9 | WMKJ-WMKK | Johor Bahru | Sepang (KLIA) | 457 |
| 10 | RPLL-WMKK | Manila | Sepang (KLIA) | 431 |

### Busiest hours (`rpt_busiest_hours`)

One row per airport and hour of the day in Malaysia time, with departures, arrivals and a rank within each airport. Departures are counted at `first_seen` and arrivals at `last_seen`. The three busiest hours at each airport:

| Airport | Busiest hours (Malaysia time) | Avg. movements per day in the busiest hour |
| --- | --- | ---: |
| KLIA (`WMKK`) | 15:00, 14:00, 16:00 | 40.8 |
| Kota Kinabalu (`WBKK`) | 15:00, 16:00, 17:00 | 11.8 |
| Subang (`WMSA`) | 13:00, 10:00, 12:00 | 6.5 |
| Penang (`WMKP`) | 18:00, 08:00, 09:00 | 4.7 |

### Flights per airline (`rpt_flights_per_airline`)

One row per airline code, with the airline name and share of all flights.

| Rank | Airline | Flights | Share |
| ---: | --- | ---: | ---: |
| 1 | AirAsia (`AXM`) | 16,624 | 33.0% |
| 2 | Malaysia Airlines (`MAS`) | 9,171 | 18.2% |
| 3 | Batik Air Malaysia (`MXD`) | 4,408 | 8.7% |
| 4 | Firefly (`FFM`) | 2,606 | 5.2% |
| 5 | `BNE` (unconfirmed, see below) | 1,146 | 2.3% |
| 6 | No callsign | 1,128 | 2.2% |
| 7 | Indonesia AirAsia (`AWQ`) | 982 | 1.9% |
| 8 | China Southern Airlines (`CSN`) | 951 | 1.9% |
| 9 | Scoot (`TGW`) | 890 | 1.8% |
| 10 | AirAsia X (`XAX`) | 778 | 1.5% |

Some names in OpenFlights are out of date. The mart shows `MXD` as "Malindo Air" (now Batik Air Malaysia) and `TGW` as "Tiger Airways" (now Scoot); the table above uses the current names. OpenFlights lists `BNE` as Benina Air, a Libyan airline, but these flights use Malaysian-registered aircraft (e.g. `9M-MWJ`), so that name is wrong. The operator hasn't been confirmed yet. All three are candidates for `airline_overrides.csv`.

## Data notes

Observations from the raw data, based on 12,639 flights across 14 days loaded so far (September–October 2026):

- **Callsigns are padded to 8 characters with trailing spaces**, for example `"MAS066  "`. They need trimming before joins or display.
- **The other airport is often unknown.** 52% of arrivals have a null `estDepartureAirport`, and 42% of departures have a null `estArrivalAirport`. This happens when OpenSky didn't track the aircraft near the other end of the flight.
- **The same aircraft appears many times a day.** `icao24` identifies the aircraft, not the flight. On a given day, 53% of aircraft appear more than once: they fly several legs, appear as both an arrival and a departure at the same airport, or fly between two of the four airports. A flight key needs `icao24` plus timing, not `icao24` alone.
- **The aircraft database is incomplete.** 91% of aircraft (2,353 of 2,574) matched to OpenSky's aircraft database (August 2025 snapshot). Unmatched aircraft are mostly newer airframes not yet in that snapshot. Of the 2,353 that matched, `typecode` is filled for almost all of them, but `operator` is blank for 76% and `operator_icao` for 41%. For the airline, the callsign prefix joined to the `airlines` seed is the more reliable source.
- **`firstSeen` and `lastSeen` are not take-off and landing times.** They are the Unix timestamps (seconds, UTC) at which OpenSky's receivers first and last picked up the aircraft. They're close to the real times, but they depend on receiver coverage.
- **`flight_duration_minutes` is tracked time, not block time.** In `fct_flights` it's `last_seen − first_seen`, so it covers only the time OpenSky was tracking the aircraft, which is roughly the airborne part of the flight. Taxiing and time on the ground aren't included. On short routes it comes to about half the scheduled block time, so don't compare it with airline timetables.

### Deduplication rule

A flight between two of the four airports, such as KLIA → Penang, is returned twice: once as a departure from KLIA and once as an arrival at Penang. To find a rule for removing these duplicates, this query groups `stg_flights` by `icao24` and `first_seen` and checks whether the copies agree:

```sql
WITH dupes AS (
    SELECT
        icao24,
        first_seen,
        COUNT(*) AS copies,
        COUNT(DISTINCT last_seen) AS different_last_seen,
        COUNT(DISTINCT est_arrival_airport) AS different_arrival,
        COUNT(DISTINCT query_date) AS different_query_dates
    FROM analytics.stg_flights
    GROUP BY icao24, first_seen
    HAVING COUNT(*) > 1
)
SELECT
    COUNT(*) AS duplicated_flights,
    MAX(copies) AS max_copies,
    COUNT(*) FILTER (WHERE different_last_seen > 1 OR different_arrival > 1) AS copies_that_disagree,
    COUNT(*) FILTER (WHERE different_query_dates > 1) AS cross_date_duplicates
FROM dupes;
```

| duplicated_flights | max_copies | copies_that_disagree | cross_date_duplicates |
| ---: | ---: | ---: | ---: |
| 707 | 2 | 0 | 48 |

What it shows:

- **707 flights were seen at both ends.** These are flights between two of the four airports. Without deduplication, each one would be counted twice.
- **The copies are identical.** No flight has more than 2 copies (`max_copies = 2`), and no copies disagree on `last_seen` or the arrival airport (`copies_that_disagree = 0`), so it doesn't matter which copy is kept. The rule **`icao24` + `first_seen` = one flight** holds.
- **48 duplicates span two dates.** For these flights, the departure and arrival copies have different `query_date`s, for example a late-night departure that arrives after midnight UTC. Deduplication must therefore work across all dates, never within a single day.

`fct_flights` applies this rule. It keeps one row per `icao24` + `first_seen` across all dates, and it also drops rows with a null `first_seen`, because a flight can't be identified without it. In the current data:

| Step | Rows |
| --- | ---: |
| `stg_flights` | 12,639 |
| Null `first_seen` removed (raw.flights id 6894) | −1 |
| Duplicate copies removed | −707 |
| **`fct_flights`** | **11,931** |

## Known limitations

- **Resuming a backfill is manual.** The pipeline doesn't yet read `raw.api_runs` to skip days that already loaded.
- **The ingestion code has few automated tests.** dbt tests cover the staging models and all marts, but pytest only covers date and argument handling ([tests/test_dates.py](tests/test_dates.py)), the API client ([tests/test_extract.py](tests/test_extract.py)) and the run logic in `run_day` ([tests/test_run_day.py](tests/test_run_day.py)) so far, using fakes, so they use no credits or database. The token manager and loading aren't tested yet. Run them with `make test`, which calls `python -m pytest` because plain `pytest` can't find the `ingestion` package. Importing `ingestion` needs the variables from `.env` to be set, though the tests never use their values.
- **8 aircraft have an operator code that isn't in `stg_airlines`** (as of 2026-11-02), down from 17 before the `airline_overrides` seed was added. The relationship test on `stg_aircraft.operator_icao` is set to warn rather than fail for this reason.

## Roadmap

- [ ] dbt staging models: trim callsigns, convert Unix times to timestamps, deduplicate flights
- [x] dbt reporting marts: top routes, busiest hours by airport, flights per airline
- [ ] dbt marts: daily traffic trends over time
- [x] CI with GitHub Actions: pytest, and `dbt build` against a throwaway Postgres
- [ ] More pytest tests for ingestion: the token manager and loading (dates, arguments, the API client and `run_day` are done)
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
