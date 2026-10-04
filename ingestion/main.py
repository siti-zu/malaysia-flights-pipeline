from ingestion.extract import OpenSkyClient
from datetime import date, datetime, timedelta, timezone
import argparse

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
    arrivals = client.get_flights(airport="WMKK", direction="arrival", query_date=query_date)

    print(f"Number of arrivals for WMKK: {len(arrivals)}")

if __name__ == "__main__":
    main()