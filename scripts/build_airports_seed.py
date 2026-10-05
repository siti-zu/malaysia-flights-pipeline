"""Build the dbt airports seed from the OurAirports airports.csv file.

Keeps large and medium airports worldwide that have a valid 4-letter ICAO code
and writes malaysia_flights_dbt/seeds/airports.csv with columns airport_code,
airport_name, city, country_code, latitude, longitude.

Usage:
    python -m scripts.build_airports_seed  (from the repo root)
"""

import csv
import io
import re
from pathlib import Path

import requests

SOURCE_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "malaysia_flights_dbt" / "seeds" / "airports.csv"

AIRPORT_TYPES = {"large_airport", "medium_airport"}
ICAO_PATTERN = re.compile(r"^[A-Z]{4}$")


def main() -> None:
    response = requests.get(SOURCE_URL, timeout=60)
    response.raise_for_status()
    response.encoding = "utf-8"
    text = response.text

    airports: dict[str, list[str]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        if row["type"] not in AIRPORT_TYPES:
            continue
        # icao_code is blank for some airports whose ident is still their ICAO code.
        icao = (row["icao_code"] or row["ident"]).strip().upper()
        if not ICAO_PATTERN.match(icao):
            continue
        airports[icao] = [
            icao,
            row["name"].strip(),
            row["municipality"].strip(),
            row["iso_country"].strip(),
            row["latitude_deg"],
            row["longitude_deg"],
        ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["airport_code", "airport_name", "city", "country_code", "latitude", "longitude"])
        for icao in sorted(airports):
            writer.writerow(airports[icao])

    print(f"Wrote {len(airports)} airports to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
