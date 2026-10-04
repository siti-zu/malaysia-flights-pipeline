from ingestion.extract import OpenSkyClient
from datetime import date, datetime, timedelta, timezone
from ingestion.load import load_flights
from ingestion.config import DIRECTIONS, AIRPORTS
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
    for airport in AIRPORTS:
        for direction in DIRECTIONS:
            flights = client.get_flights(airport=airport, direction=direction, query_date=query_date)
            loaded_count = load_flights(flights, airport=airport, direction=direction, query_date=query_date)
            print(f"{airport} {direction} {query_date}: {loaded_count} rows loaded into the database.")

if __name__ == "__main__":
    main()