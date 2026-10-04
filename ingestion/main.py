import requests
import json
from datetime import datetime, timedelta, timezone
from ingestion.config import BASE_URL, BASE_DIR, REQUEST_TIMEOUT
from ingestion.auth import TokenManager

def yesterday_utc_window():
    """Return the begin and end timestamps for the previous day in UTC."""
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    begin = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59, tzinfo=timezone.utc)
    return int(begin.timestamp()), int(end.timestamp())

def main():
    token_manager = TokenManager()
    headers = token_manager.headers()

    begin, end = yesterday_utc_window()
    print(f"Begin: {begin}, End: {end}")

    params = {
        "airport": "WMKK",
        "begin": begin,
        "end": end
    }
    response = requests.get(f"{BASE_URL}/flights/arrival", headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    print(f"Status Code: {response.status_code}")
    print(f"X-Rate-Limit-Remaining: {response.headers.get('X-Rate-Limit-Remaining')}")

    if response.status_code == 200:
        flights = response.json()
        print(f"Number of arrivals for WMKK: {len(flights)}")

        output_file = BASE_DIR / "tests" / "fixtures" / "wmkk_arrivals_sample.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump(flights, f, indent=4)
    else:
        print(f"Error fetching arrivals for WMKK. Status: {response.status_code}")

if __name__ == "__main__":
    main()