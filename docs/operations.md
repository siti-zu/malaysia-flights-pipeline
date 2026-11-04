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

- **`pytest`** runs the Python tests. It uses dummy environment variables, because `config.py` won't import without them and the tests never use their values.
- **`dbt`** starts a throwaway Postgres, creates the raw tables with [sql/init.sql](../sql/init.sql), then runs `dbt deps` and `dbt build`.

The raw tables are empty in CI, because the job doesn't call OpenSky. So `dbt build` proves that the project compiles, every model's SQL runs, the seeds load and tests on the seeds pass, but tests on flight data have no rows to check.
