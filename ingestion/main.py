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

    group = parser.add_mutually_exclusive_group()

    group.add_argument("--date", type=date.fromisoformat,
                       help="Single date in YYYY-MM-DD format.")
    group.add_argument("--start", type=date.fromisoformat,
                       help="First date of an inclusive range, in YYYY-MM-DD format.")
    group.add_argument("--days", type=int, metavar="N",
                       help="Fetch the last N days, ending yesterday (UTC) inclusive.")
    parser.add_argument("--end", type=date.fromisoformat,
                        help="Last date of the range, inclusive, in YYYY-MM-DD format. "
                             "Requires --start. Defaults to yesterday (UTC).")
    args = parser.parse_args()
    validate_and_fill_args(parser, args)
    return args

def validate_and_fill_args(parser, args):
    # UTC to match the default query date in main().
    yesterday = yesterday_utc()

    if args.end is not None and args.start is None:
        parser.error("--end requires --start.")

    for name in ("date", "start", "end"):
        value = getattr(args, name)
        if value is not None and value > yesterday:
            parser.error(f"--{name} must be {yesterday} or earlier.")

    if args.start is not None:
        if args.end is None:
            args.end = yesterday
        if args.start > args.end:
            parser.error("--start cannot be after --end.")

    if args.days is not None and args.days < 1:
        parser.error("--days must be at least 1.")

def yesterday_utc():
    """Return yesterday's date in UTC."""
    return datetime.now(timezone.utc).date() - timedelta(days=1)

def get_query_dates(args):
    if args.date is not None:
        return [args.date]
    elif args.start is not None:
        return [args.start + timedelta(days=i) for i in range((args.end - args.start).days + 1)]
    elif args.days is not None:
        yesterday = yesterday_utc()
        first_day = yesterday - timedelta(days=args.days - 1)
        return [first_day + timedelta(days=i) for i in range(args.days)]
    else:
        return [yesterday_utc()]

def run_day(client, query_date):
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
            print(f"Stopping run on {query_date}: HTTP {status_code} will affect all remaining calls.")
            break

    print(f"Done: {attempted - failures} of {attempted} calls succeeded "
            f"({len(pairs) - attempted} skipped).")

    return failures, stopped_early

def main():
    args = parse_args()
    query_dates = get_query_dates(args)

    client = OpenSkyClient()
    total_failures = 0
    stopped_early = False

    for query_date in query_dates:
        failures, stopped_early = run_day(client, query_date)
        total_failures += failures

        if stopped_early:
            break

    print(f"Processed {len(query_dates) - total_failures} of {len(query_dates)} days, {total_failures} calls failed.")

    if total_failures:
            sys.exit(1)

if __name__ == "__main__":
    main()