# Data model and seeds

The details behind the [README](../README.md): the tables, how each seed is built, and what the raw data looks like.

## Raw tables

**`raw.flights`**: one row per flight returned by the API. It stores the airport and direction queried, the UTC day requested, the run ID, a load timestamp, and the flight itself as untouched JSON in `payload`.

**`raw.api_runs`**: one row per API call, successful or not. It records the HTTP status, rows returned, credits left and any error message, and is used for monitoring, debugging and resuming backfills.

The full schema is in [sql/init.sql](../sql/init.sql).

## Marts

**Marts** (`analytics` schema, built by dbt as tables): a star schema with `fct_flights` at the centre and three dimensions. Each dimension has one row per key, and its key has `unique` and `not_null` tests.

| Model | Grain | Joins to `fct_flights` on |
| --- | --- | --- |
| `fct_flights` | One row per flight, deduplicated (see the [dedupe rule](../README.md#the-dedupe-rule)) | — |
| `dim_airline` | One row per ICAO airline code | `airline_code` |
| `dim_aircraft` | One row per aircraft seen in the flight data | `icao24` |
| `dim_airport` | One row per airport code: large and medium airports worldwide, plus any airport used in the flight data | `est_departure_airport` or `est_arrival_airport` |

Not every flight has a match, so always join the dimensions with a `LEFT JOIN`. An inner join would drop those flights.

## Reporting marts

Each mart has a test on its grain, so a join that fans out fails the build instead of quietly inflating the counts. That can happen if a dimension ever gets two rows for the same key, or if a mart joins on something that isn't unique, such as an airport's name or city: the old and new Dhaka codes (`VGZR` and `VGHS`) are two rows for the same airport. `rpt_top_routes` has a `unique` test on `route`. `rpt_busiest_hours` (one row per airport and hour) and `rpt_flights_per_airline` (one row per airline code) use `dbt_utils.unique_combination_of_columns`. Unlike `unique`, it also catches duplicate rows with a null key.

## Seeds

The seed scripts live in [scripts/](../scripts/) and are run as modules from the repo root, like the ingestion. That way `scripts.build_aircraft_seed` can import `ingestion` without changing `sys.path`. `make seeds` runs all three.

**`airlines` seed**: a dbt seed at [malaysia_flights_dbt/seeds/airlines.csv](../malaysia_flights_dbt/seeds/airlines.csv) that maps 3-letter ICAO airline codes (`airline_code`) to names (`airline_name`), so airlines can be identified from the first three letters of a callsign. It's built from OpenFlights' `airlines.dat`. Some ICAO codes appear more than once in that file, because codes from defunct airlines get reused, so the seed keeps one name per code and prefers the active airline. To regenerate it:

```bash
python -m scripts.build_airlines_seed
```

**`airports` seed**: a dbt seed at [malaysia_flights_dbt/seeds/airports.csv](../malaysia_flights_dbt/seeds/airports.csv) that maps 4-letter ICAO airport codes (`airport_code`) to `airport_name`, `city`, `country_code` (ISO 3166-1 alpha-2), `latitude` and `longitude`. It's built from OurAirports' `airports.csv`. It covers the whole world, because flights go to destinations everywhere, and keeps two sets of airports (about 5,000 rows):

- **Every `large_airport` and `medium_airport`** with a 4-letter ICAO code. If an airport has no `icao_code`, its `ident` is used as long as it's 4 letters.
- **Any airport, of any size, whose code appears in `raw.flights`.** This adds small Malaysian airfields such as Kota Belud (`WBKB`) and Sitiawan (`WMBA`), and small foreign ones such as Indian air force stations, without adding thousands of unused airports. A flight's code is matched against OurAirports' `icao_code`, `ident`, `gps_code` and, last, `keywords`. `keywords` holds retired codes that OpenSky still uses, such as `VGZR` for Dhaka's Hazrat Shahjalal International Airport, which is now `VGHS`. Such an airport then appears under both codes, so group by `airport_name` rather than `airport_code` to count it once.

Like the aircraft seed, the second set depends on the data: re-run the script after loading new days, with the database running. To regenerate it:

```bash
python -m scripts.build_airports_seed
```

**`aircraft` seed**: a dbt seed at [malaysia_flights_dbt/seeds/aircraft.csv](../malaysia_flights_dbt/seeds/aircraft.csv) that maps `icao24` to `registration`, `manufacturer`, `model`, `typecode`, `operator` and `operator_icao`. It's built from OpenSky's aircraft database (the `aircraft-database-complete-2025-08.csv` snapshot). That snapshot is pinned on purpose so the seed is reproducible; newer snapshots exist, and moving to one should be a deliberate change. The full file is over 100 MB, so the script keeps only the aircraft that appear in `raw.flights`. It needs the database to be running. To regenerate it:

```bash
python -m scripts.build_aircraft_seed
```

> **This seed goes stale after every load.** Like the airports seed, and unlike the airlines one, it depends on what's in `raw.flights`. Aircraft loaded by a new daily run or backfill won't have a registration, model or operator until you re-run the script and `dbt seed`. Until then they still appear in `stg_flights`, just without details, as long as models join to `stg_aircraft` with a left join.

**`airline_overrides` seed**: a hand-maintained seed at [malaysia_flights_dbt/seeds/airline_overrides.csv](../malaysia_flights_dbt/seeds/airline_overrides.csv) for airline codes that appear in the flight data but are missing from OpenFlights, such as `RMY` (Raya Airways) and `SJX` (Starlux Airlines), and for codes where its name is out of date, such as `MXD` (Batik Air Malaysia, listed as Malindo Air) and `TGW` (Scoot, listed as Tiger Airways). It has the same `airline_code` and `airline_name` columns as `airlines.csv`, plus a `source` column noting where each name was checked. No script builds it; add rows by hand. `stg_airlines` combines it with `airlines.csv`, and an override replaces the OpenFlights name if a code is in both.

## Data notes

Observations from the raw data, measured on 2026-11-03:

- **Callsigns are padded to 8 characters with trailing spaces**, for example `"MAS066  "`. They need trimming before joins or display.
- **The other airport is often unknown.** 51% of arrivals have a null `estDepartureAirport`, and 43% of departures have a null `estArrivalAirport`. This happens when OpenSky didn't track the aircraft near the other end of the flight.
- **The same aircraft appears many times a day.** `icao24` identifies the aircraft, not the flight. On a given day, 53% of aircraft appear more than once: they fly several legs, appear as both an arrival and a departure at the same airport, or fly between two of the four airports. A flight key needs `icao24` plus timing, not `icao24` alone.
- **The aircraft database is incomplete.** 91% of aircraft (2,373 of 2,596) matched to OpenSky's aircraft database (August 2025 snapshot). Unmatched aircraft are mostly newer airframes not yet in that snapshot. Of the 2,373 that matched, `typecode` is filled for almost all of them, but `operator` is blank for 76% and `operator_icao` for 41%. For the airline, the callsign prefix joined to the `airlines` seed is the more reliable source.
- **`firstSeen` and `lastSeen` are not take-off and landing times.** They are the Unix timestamps (seconds, UTC) at which OpenSky's receivers first and last picked up the aircraft. They're close to the real times, but they depend on receiver coverage.
- **`flight_duration_minutes` is tracked time, not block time.** In `fct_flights` it's `last_seen − first_seen`, so it covers only the time OpenSky was tracking the aircraft, which is roughly the airborne part of the flight. Taxiing and time on the ground aren't included. On short routes it comes to about half the scheduled block time, so don't compare it with airline timetables.
