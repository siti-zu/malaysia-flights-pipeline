"""Build the dbt airlines seed from the OpenFlights airlines.dat file.

Keeps every airline with a valid 3-letter ICAO code and writes
malaysia_flights_dbt/seeds/airlines.csv with columns airline_code, airline_name.

Usage:
    python -m scripts.build_airlines_seed  (from the repo root)
"""

import csv
import io
import re
from pathlib import Path

import requests

SOURCE_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "malaysia_flights_dbt" / "seeds" / "airlines.csv"

ICAO_PATTERN = re.compile(r"^[A-Z]{3}$")

# airlines.dat columns: id, name, alias, iata, icao, callsign, country, active
NAME, ICAO, ACTIVE = 1, 4, 7


def main() -> None:
    response = requests.get(SOURCE_URL, timeout=30)
    response.raise_for_status()
    response.encoding = "utf-8"
    text = response.text

    # ICAO codes aren't unique in OpenFlights (defunct airlines reuse them),
    # so keep one name per code, preferring the active airline.
    airlines: dict[str, tuple[str, bool]] = {}
    for row in csv.reader(io.StringIO(text)):
        icao = row[ICAO].strip().upper()
        name = row[NAME].strip()
        active = row[ACTIVE] == "Y"
        if not ICAO_PATTERN.match(icao) or not name or name == r"\N":
            continue
        if icao not in airlines or (active and not airlines[icao][1]):
            airlines[icao] = (name, active)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["airline_code", "airline_name"])
        for icao in sorted(airlines):
            writer.writerow([icao, airlines[icao][0]])

    print(f"Wrote {len(airlines)} airlines to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
