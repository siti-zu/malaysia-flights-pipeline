from datetime import date, datetime, timedelta, timezone
import itertools
import sys

import requests
import argparse

from ingestion.extract import OpenSkyClient, parse_remaining_credits
from ingestion.load import load_flights, log_api_run
from ingestion.config import DIRECTIONS, AIRPORTS

# Errors that mean every remaining call will fail too, so stop the run.
STOP_RUN_STATUSES = {401, 429}

def parse_args():
    parser = argparse.ArgumentParser(description="Fetch flight data from OpenSky API.")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="Date in YYYY-MM-DD format.")
    return parser.parse_args()

def main():
    args = parse_args()
    query_date = args.date
    if query_date is None:
        query_date = datetime.now(timezone.utc).date() - timedelta(days=1)  # Default to yesterday's date

    client = OpenSkyClient()
    pairs = list(itertools.product(AIRPORTS, DIRECTIONS))
    attempted = failures = 0
    stopped_early = False

    for airport, direction in pairs:
        attempted += 1
        label = f"{airport} {direction} {query_date}"

        # Fresh values for every call, so nothing leaks from the previous one.
        status_code = row_count = credits_left = error_message = None

        try:
            result = client.get_flights(
                airport=airport, direction=direction, query_date=query_date
            )
            status_code = result.status_code
            credits_left = result.credits_left
            row_count = len(result.flights)

            load_flights(
                result.flights, airport=airport, direction=direction, query_date=query_date
            )
            print(f"{label}: {row_count} rows loaded")

        except requests.HTTPError as e:
            status_code = e.response.status_code
            credits_left = parse_remaining_credits(e.response)
            error_message = str(e)
            failures += 1
            print(f"{label}: HTTP {status_code}: {e}")
            stopped_early = status_code in STOP_RUN_STATUSES

        except Exception as e:
            error_message = f"{type(e).__name__}: {e}"
            failures += 1
            print(f"{label}: {error_message}")

        log_api_run(
            airport=airport,
            direction=direction,
            query_date=query_date,
            status_code=status_code,
            row_count=row_count,
            credits_left=credits_left,
            error_message=error_message,
        )

        if stopped_early:
            print(f"Stopping run: HTTP {status_code} will affect all remaining calls.")
            break

    print(f"Done: {attempted - failures} of {attempted} calls succeeded "
          f"({len(pairs) - attempted} skipped).")
    
    if failures:
        sys.exit(1)

if __name__ == "__main__":
    main()