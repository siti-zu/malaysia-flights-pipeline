"""Load a small sample of real flights, so dbt has data to test without calling OpenSky.

CI runs this before dbt build. It replaces whole days, so it refuses to run
unless the raw tables are empty, which protects a real database.

Run with:
    python -m scripts.load_sample_flights  (from the repo root)
"""
import json
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

from ingestion.load import get_connection, load_flights, log_api_run

SAMPLE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_raw_flights.json"


def main():
    slices = json.loads(SAMPLE_PATH.read_text())
    run_id = uuid4()

    with get_connection() as conn:
        has_data = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM raw.flights) OR EXISTS (SELECT 1 FROM raw.api_runs)"
        ).fetchone()[0]
        if has_data:
            sys.exit("Raw tables already have data, so the sample was not loaded.")

        for item in slices:
            query_date = date.fromisoformat(item["query_date"])
            row_count = load_flights(conn, item["flights"], item["airport"], item["direction"], query_date, run_id)
            log_api_run(conn, item["airport"], item["direction"], query_date, run_id,
                        status_code=200, row_count=row_count)

    print(f"Loaded {len(slices)} slices.")


if __name__ == "__main__":
    main()
