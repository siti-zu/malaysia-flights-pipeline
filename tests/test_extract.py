import json
from datetime import date
from pathlib import Path

import pytest
import requests

from ingestion.config import BASE_URL
from ingestion.extract import OpenSkyClient, create_retry_session, parse_remaining_credits

QUERY_DATE = date(2026, 9, 15)
SAMPLE_FLIGHTS = json.loads((Path(__file__).parent / "fixtures" / "wmkk_arrivals_sample.json").read_text())


class FakeTokenManager:
    def headers(self):
        return {"Authorization": "Bearer test-token"}


class FakeSession:
    """Stands in for the requests session: returns one response and records each call."""

    def __init__(self, response=None):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


def make_response(status_code, flights=None, credits_left=None):
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(flights if flights is not None else {}).encode()
    if credits_left is not None:
        response.headers["X-Rate-Limit-Remaining"] = str(credits_left)
    return response


def make_client(response=None):
    client = OpenSkyClient(token_manager=FakeTokenManager())
    client.session = FakeSession(response)
    return client


def test_200_returns_flights_status_and_credits():
    client = make_client(make_response(200, flights=SAMPLE_FLIGHTS, credits_left=3500))

    result = client.get_flights("WMKK", "arrival", QUERY_DATE)

    assert result.flights == SAMPLE_FLIGHTS
    assert result.status_code == 200
    assert result.credits_left == 3500


def test_request_asks_for_the_right_airport_direction_and_day():
    client = make_client(make_response(200, flights=[]))

    client.get_flights("WMKK", "departure", QUERY_DATE)

    assert len(client.session.calls) == 1
    call = client.session.calls[0]
    assert call["url"].endswith("/flights/departure")
    assert call["params"] == {"airport": "WMKK", "begin": 1789430400, "end": 1789516799}
    assert call["headers"] == {"Authorization": "Bearer test-token"}


def test_404_returns_an_empty_list_not_an_error():
    client = make_client(make_response(404, credits_left=3499))

    result = client.get_flights("WMKK", "arrival", QUERY_DATE)

    assert result.flights == []
    assert result.status_code == 404
    assert result.credits_left == 3499


@pytest.mark.parametrize("status_code", [429, 500])
def test_error_statuses_raise_http_error(status_code):
    client = make_client(make_response(status_code, credits_left=0))

    with pytest.raises(requests.HTTPError) as exc_info:
        client.get_flights("WMKK", "arrival", QUERY_DATE)

    # run_day reads the status and credits from the error's response.
    assert exc_info.value.response.status_code == status_code
    assert parse_remaining_credits(exc_info.value.response) == 0


def test_invalid_direction_raises_before_any_request():
    client = make_client()

    with pytest.raises(ValueError, match="Invalid direction 'sideways'"):
        client.get_flights("WMKK", "sideways", QUERY_DATE)

    assert client.session.calls == []


def test_day_window_is_midnight_to_last_second_utc():
    client = make_client()

    begin, end = client._get_day_window(QUERY_DATE)

    # 2026-09-15 00:00:00 and 23:59:59 UTC, written out so they don't depend on
    # the same date logic as the code under test.
    assert begin == 1789430400
    assert end == 1789516799


def test_parse_remaining_credits_reads_the_header():
    response = make_response(200, credits_left=42)

    assert parse_remaining_credits(response) == 42


def test_parse_remaining_credits_is_none_when_header_is_missing():
    response = make_response(200)

    assert parse_remaining_credits(response) is None


def test_retry_session_retries_server_errors_for_the_api_url():
    session = create_retry_session()

    retry = session.get_adapter(BASE_URL).max_retries

    # An exact match, so 429 can't slip in: retrying it would only hit the credit limit again.
    assert retry.status_forcelist == [500, 502, 503, 504]
    assert retry.total == 3
    assert retry.backoff_factor == 1
    # False so the last 5xx comes back as a response and raise_for_status gives an HTTPError.
    assert retry.raise_on_status is False
