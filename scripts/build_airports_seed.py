"""Build the dbt airports seed from the OurAirports airports.csv file.

Keeps two sets of airports and writes malaysia_flights_dbt/seeds/airports.csv
with columns airport_code, airport_name, city, country_code, latitude, longitude:

- every large and medium airport worldwide with a valid 4-letter ICAO code, and
- any airport, of any size, whose code appears in raw.flights. This covers small
  Malaysian airfields and small foreign airports without adding thousands of
  unused ones. Re-run it after loading new days to pick up new airports.

Usage:
    python -m scripts.build_airports_seed  (from the repo root)
"""

import csv
import io
import re
from pathlib import Path

import requests

from ingestion.load import get_connection

SOURCE_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "malaysia_flights_dbt" / "seeds" / "airports.csv"

AIRPORT_TYPES = {"large_airport", "medium_airport"}
ICAO_PATTERN = re.compile(r"^[A-Z]{4}$")

# OurAirports columns a flight's airport code can match, best match first.
# Small airfields often have no icao_code, and OpenSky then uses their ident or
# gps_code, which can contain digits (e.g. OM11). Retired codes that OpenSky
# still uses live in keywords, e.g. VGZR for Dhaka (now VGHS).
CODE_COLUMNS = ["icao_code", "ident", "gps_code", "keywords"]


def flight_airport_codes() -> set[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT payload->>'estDepartureAirport' FROM raw.flights
            UNION
            SELECT payload->>'estArrivalAirport' FROM raw.flights
            UNION
            SELECT airport FROM raw.flights
            """
        ).fetchall()
    return {row[0].strip().upper() for row in rows if row[0]}


def to_seed_row(code: str, row: dict[str, str]) -> list[str]:
    return [
        code,
        row["name"].strip(),
        row["municipality"].strip(),
        row["iso_country"].strip(),
        row["latitude_deg"],
        row["longitude_deg"],
    ]


def main() -> None:
    wanted = flight_airport_codes()
    print(f"Found {len(wanted)} distinct airport codes in raw.flights")

    response = requests.get(SOURCE_URL, timeout=60)
    response.raise_for_status()
    response.encoding = "utf-8"
    text = response.text

    airports: dict[str, list[str]] = {}
    # For codes from raw.flights: the best (rank, row) seen so far. A code can
    # match more than one OurAirports row, e.g. a closed airfield's ident and an
    # open one's gps_code; prefer open airports, then an icao_code match.
    flight_matches: dict[str, tuple[tuple[bool, int], list[str]]] = {}

    for row in csv.DictReader(io.StringIO(text)):
        if row["type"] in AIRPORT_TYPES:
            # icao_code is blank for some airports whose ident is still their ICAO code.
            icao = (row["icao_code"] or row["ident"]).strip().upper()
            if ICAO_PATTERN.match(icao):
                airports[icao] = to_seed_row(icao, row)

        for position, column in enumerate(CODE_COLUMNS):
            if column == "keywords":
                codes = {k.strip().upper() for k in row[column].split(",")} & wanted
            else:
                codes = {row[column].strip().upper()} & wanted
            if not codes:
                continue
            code = codes.pop()
            rank = (row["type"] != "closed", -position)
            if code not in flight_matches or rank > flight_matches[code][0]:
                flight_matches[code] = (rank, to_seed_row(code, row))

    # Large and medium airports keep their own row; flights only fill the gaps.
    added = 0
    for code, (_, seed_row) in flight_matches.items():
        if code not in airports:
            airports[code] = seed_row
            added += 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["airport_code", "airport_name", "city", "country_code", "latitude", "longitude"])
        for code in sorted(airports):
            writer.writerow(airports[code])

    missing = sorted(wanted - airports.keys())
    print(f"Wrote {len(airports)} airports to {OUTPUT_PATH} ({added} added because they appear in raw.flights)")
    if missing:
        print(f"{len(missing)} codes from raw.flights aren't in OurAirports: {', '.join(missing)}")


if __name__ == "__main__":
    main()
