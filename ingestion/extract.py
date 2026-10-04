import requests
from datetime import datetime, timezone
from ingestion.auth import TokenManager
from ingestion.config import BASE_URL, DIRECTIONS, REQUEST_TIMEOUT

class OpenSkyClient:
    def __init__(self, token_manager=None):
        self.token_manager = token_manager or TokenManager()
        self.session = requests.Session()

    def _get_day_window(self, query_date):
        """Return the begin and end timestamps for the specified date in UTC."""
        begin = datetime(query_date.year, query_date.month, query_date.day, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(query_date.year, query_date.month, query_date.day, 23, 59, 59, tzinfo=timezone.utc)
        return int(begin.timestamp()), int(end.timestamp())

    def get_flights(self, airport, direction, query_date):
        if direction not in DIRECTIONS:
            raise ValueError(f"Invalid direction '{direction}'. Please use one of the following: {', '.join(DIRECTIONS)}")

        headers = self.token_manager.headers()
        begin, end = self._get_day_window(query_date)

        params = {
            "airport": airport,
            "begin": begin,
            "end": end
        }
        response = self.session.get(f"{BASE_URL}/flights/{direction}", headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        print(f"Status Code: {response.status_code}")
        print(f"X-Rate-Limit-Remaining: {response.headers.get('X-Rate-Limit-Remaining')}")

        if response.status_code == 404:
            print(f"No data found for {airport} {direction} flights on {query_date}.")
            return []

        response.raise_for_status()
        return response.json()