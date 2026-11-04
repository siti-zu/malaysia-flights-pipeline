# Running the pipeline

The details behind the [README](../README.md): the daily schedule, the credit budget, CI and the Make commands.

## Commands

Run `make help` to list every command. `make charts` redraws the README charts from the reporting marts.

## Credit budget

OpenSky charges 30 credits per call for these endpoints, so one day of data costs 8 × 30 = **240 credits**. The remaining balance is recorded on every row of `raw.api_runs`.

Backfills that hit the daily credit limit stop cleanly on the `429`. To resume, check `raw.api_runs` for the last day that completed and re-run with `--start` set to the day after it. Because loads are idempotent, starting from a day that was already partly loaded is safe.

## Daily schedule

On a Mac, launchd runs [scripts/daily_run.sh](../scripts/daily_run.sh) every day at 13:00 local time, by when OpenSky has yesterday's data. The script starts Postgres, runs `make ingest`, then runs `make transform` only if the ingest succeeded. It appends all output to `logs/daily.log`, and each run starts and ends with a timestamped line, the last one giving the exit code.

The job is defined in [scripts/com.siti-zu.malaysia-flights.daily.plist](../scripts/com.siti-zu.malaysia-flights.daily.plist), which contains absolute paths, so change them if your username or repo folder is different. To install it:

```bash
cp scripts/com.siti-zu.malaysia-flights.daily.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.siti-zu.malaysia-flights.daily.plist
```

```bash
launchctl kickstart gui/$(id -u)/com.siti-zu.malaysia-flights.daily                          # run it now
launchctl print gui/$(id -u)/com.siti-zu.malaysia-flights.daily | grep "last exit code"      # check the last run
launchctl bootout gui/$(id -u)/com.siti-zu.malaysia-flights.daily                            # remove the schedule
```

After changing the plist, copy it again and run `bootout` then `bootstrap` for the change to apply.

What it doesn't handle:

- **The Mac has to be on, and Docker Desktop running.** If the Mac is asleep at 13:00, the job runs when it wakes. If it's shut down, that run is skipped. If Docker Desktop isn't running, `make up` fails and the run stops before spending any credits.
- **Missed days aren't caught up automatically.** Each run only loads yesterday. Once a later day has loaded, the completeness test fails for the gap, so `make transform` exits with an error. Fix it with `make backfill START=<missed day> END=<missed day>`.
- **Failure alerts only reach this Mac.** A failed run shows a macOS notification, and the details are in `logs/daily.log`. If macOS blocks it, allow notifications for Script Editor in System Settings. A run that never starts, such as when the Mac is shut down, shows nothing, so `make freshness` is still worth running now and then.
- **The seeds aren't refreshed.** Aircraft and airports first seen after the last `make seeds` stay unmatched until you run it again.

## CI

[.github/workflows/ci.yml](../.github/workflows/ci.yml) runs on every push to `main` and every pull request, with two jobs:

- **`pytest`** starts a throwaway Postgres, creates the raw tables with [sql/init.sql](../sql/init.sql) and runs the Python tests. OpenSky is faked, so its credentials are dummy values, which `config.py` needs in order to import.
- **`dbt`** starts a throwaway Postgres, creates the raw tables, loads the sample flights, then runs `dbt deps` and `dbt build`.

CI doesn't call OpenSky, so [scripts/load_sample_flights.py](../scripts/load_sample_flights.py) loads [a sample of real flights](../tests/fixtures/sample_raw_flights.json): 323 rows from 2026-09-11 to 09-13, taken from about 1 in 10 aircraft. It deliberately includes a null `first_seen` and flights returned on two dates, so the dedupe and the null filter have real work to do. The script refuses to run if the raw tables already have data, because it would replace real days. `dbt_utils.at_least_one` fails the build if `fct_flights` or `rpt_daily_traffic` is empty, since other tests would pass on an empty table.

The loading tests in `make test` need Postgres. Locally they're skipped if it isn't running, and in CI they fail instead. They write inside a transaction that's always rolled back, using an airport code real data can't have, so they're safe to run against your real database.
