"""Build the dbt aircraft seed from OpenSky's aircraft database.

The full database is over 100 MB, far too big for a seed, so this keeps only the
aircraft (icao24 values) that appear in raw.flights. Re-run it after loading new
days to pick up aircraft seen for the first time.

Writes malaysia_flights_dbt/seeds/aircraft.csv with columns icao24, registration,
manufacturer, model, typecode, operator, operator_icao.

Usage:
    python -m scripts.build_aircraft_seed  (from the repo root)
"""

import csv
import io
from pathlib import Path

import requests

from ingestion.load import get_connection

REPO_ROOT = Path(__file__).resolve().parent.parent

# Pinned on purpose so the seed is reproducible. OpenSky publishes newer
# snapshots (aircraft-database-complete-YYYY-MM.csv in the same bucket); bump
# this deliberately and review the seed diff when you do.
SOURCE_URL = "https://s3.opensky-network.org/data-samples/metadata/aircraft-database-complete-2025-08.csv"
OUTPUT_PATH = REPO_ROOT / "malaysia_flights_dbt" / "seeds" / "aircraft.csv"

# Output column -> column in the OpenSky file.
COLUMNS = {
    "icao24": "icao24",
    "registration": "registration",
    "manufacturer": "manufacturerName",
    "model": "model",
    "typecode": "typecode",
    "operator": "operator",
    "operator_icao": "operatorIcao",
}


def flight_icao24s() -> set[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT lower(payload->>'icao24') FROM raw.flights WHERE payload->>'icao24' IS NOT NULL"
        ).fetchall()
    return {row[0] for row in rows}


def main() -> None:
    wanted = flight_icao24s()
    print(f"Found {len(wanted)} distinct aircraft in raw.flights")

    # The file can list an aircraft more than once; keep its most recent record.
    aircraft: dict[str, dict[str, str]] = {}
    # Stream the file rather than holding all 100+ MB in memory.
    with requests.get(SOURCE_URL, stream=True, timeout=60) as response:
        response.raise_for_status()
        response.raw.decode_content = True
        response.raw.auto_close = False  # otherwise TextIOWrapper sees a closed file
        # OpenSky quotes values with single quotes, not double quotes.
        reader = csv.DictReader(io.TextIOWrapper(response.raw, encoding="utf-8", newline=""), quotechar="'")
        for row in reader:
            icao24 = row["icao24"].strip().lower()
            if icao24 not in wanted:
                continue
            # Timestamps are compared as text, which orders correctly because every
            # row uses "YYYY-MM-DD HH:MM:SS" (checked across all 616,675 rows of the
            # 2025-08 snapshot). Re-check if you change SOURCE_URL.
            if icao24 in aircraft and row["timestamp"] <= aircraft[icao24]["timestamp"]:
                continue
            aircraft[icao24] = row

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for icao24 in sorted(aircraft):
            row = aircraft[icao24]
            writer.writerow([icao24] + [row[src].strip() for src in list(COLUMNS.values())[1:]])

    print(f"Wrote {len(aircraft)} aircraft to {OUTPUT_PATH} ({len(wanted) - len(aircraft)} not in the OpenSky database)")


if __name__ == "__main__":
    main()
