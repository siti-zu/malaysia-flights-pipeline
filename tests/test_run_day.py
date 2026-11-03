from datetime import date
from itertools import product
from uuid import uuid4

import psycopg
import pytest
import requests

from ingestion import main
from ingestion.config import AIRPORTS, DIRECTIONS
from ingestion.extract import FlightsResult
from ingestion.main import run_day

QUERY_DATE = date(2026, 9, 15)
RUN_ID = uuid4()
ALL_PAIRS = list(product(AIRPORTS, DIRECTIONS))
FLIGHTS = [{"icao24": "750541"}, {"icao24": "750542"}]


class FakeClient:
    """Returns flights for every call, except the pairs given an exception or result in outcomes."""

    def __init__(self, outcomes=None):
        self.outcomes = outcomes or {}
        self.calls = []

    def get_flights(self, airport, direction, query_date):
        self.calls.append((airport, direction))
        outcome = self.outcomes.get((airport, direction))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome or FlightsResult(flights=FLIGHTS, status_code=200, credits_left=3500)


class Recorder:
    """Replaces load_flights or log_api_run: records each call and can raise instead."""

    def __init__(self):
        self.calls = []
        self.errors = {}

    def __call__(self, conn, *args, **kwargs):
        self.calls.append({**kwargs, "args": args})
        error = self.errors.get((kwargs["airport"], kwargs["direction"]))
        if error:
            raise error

    def pairs(self):
        return [(call["airport"], call["direction"]) for call in self.calls]

    def for_pair(self, pair):
        return next(call for call in self.calls if (call["airport"], call["direction"]) == pair)


@pytest.fixture
def load(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(main, "load_flights", recorder)
    return recorder


@pytest.fixture
def log(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(main, "log_api_run", recorder)
    return recorder


def make_http_error(status_code, credits_left=None):
    response = requests.Response()
    response.status_code = status_code
    if credits_left is not None:
        response.headers["X-Rate-Limit-Remaining"] = str(credits_left)
    return requests.HTTPError(f"{status_code} Error", response=response)


def run(client):
    return run_day(client, None, QUERY_DATE, RUN_ID)


def test_all_calls_succeed(load, log):
    client = FakeClient()

    failures, stopped_early = run(client)

    assert (failures, stopped_early) == (0, False)
    assert client.calls == ALL_PAIRS
    assert load.pairs() == ALL_PAIRS


def test_every_call_is_logged_once(load, log):
    run(FakeClient())

    assert log.pairs() == ALL_PAIRS


def test_success_is_logged_with_its_details(load, log):
    run(FakeClient())

    call = log.calls[0]
    assert call["query_date"] == QUERY_DATE
    assert call["run_id"] == RUN_ID
    assert call["status_code"] == 200
    assert call["row_count"] == len(FLIGHTS)
    assert call["credits_left"] == 3500
    assert call["error_message"] is None


def test_flights_are_loaded_for_the_right_partition(load, log):
    run(FakeClient())

    call = load.calls[0]
    assert call["args"] == (FLIGHTS,)
    assert (call["airport"], call["direction"]) == ALL_PAIRS[0]
    assert call["query_date"] == QUERY_DATE
    assert call["run_id"] == RUN_ID


def test_404_counts_as_success_and_still_loads_the_empty_list(load, log):
    # Loading the empty list clears any old rows for that airport, direction and day.
    pair = ALL_PAIRS[0]
    client = FakeClient({pair: FlightsResult(flights=[], status_code=404, credits_left=3500)})

    failures, stopped_early = run(client)

    assert (failures, stopped_early) == (0, False)
    assert load.for_pair(pair)["args"] == ([],)
    assert log.for_pair(pair)["status_code"] == 404
    assert log.for_pair(pair)["row_count"] == 0
    assert log.for_pair(pair)["error_message"] is None


def test_500_counts_as_a_failure_and_the_other_calls_still_run(load, log):
    bad_pair = ALL_PAIRS[2]
    client = FakeClient({bad_pair: make_http_error(500, credits_left=3400)})

    failures, stopped_early = run(client)

    assert (failures, stopped_early) == (1, False)
    assert client.calls == ALL_PAIRS
    assert load.pairs() == [pair for pair in ALL_PAIRS if pair != bad_pair]
    assert log.pairs() == ALL_PAIRS


def test_http_error_is_logged_with_its_details(load, log):
    bad_pair = ALL_PAIRS[2]

    run(FakeClient({bad_pair: make_http_error(500, credits_left=3400)}))

    call = log.for_pair(bad_pair)
    assert call["status_code"] == 500
    assert call["row_count"] is None
    assert call["credits_left"] == 3400
    assert "500 Error" in call["error_message"]


@pytest.mark.parametrize("status_code", [401, 429])
def test_401_and_429_stop_the_run(status_code, load, log):
    bad_pair = ALL_PAIRS[2]
    client = FakeClient({bad_pair: make_http_error(status_code)})

    failures, stopped_early = run(client)

    assert (failures, stopped_early) == (1, True)
    assert client.calls == ALL_PAIRS[:3]
    assert load.pairs() == ALL_PAIRS[:2]
    # The call that stopped the run is logged too.
    assert log.pairs() == ALL_PAIRS[:3]
    assert log.for_pair(bad_pair)["status_code"] == status_code


def test_error_before_a_stop_does_not_hide_the_stop(load, log):
    client = FakeClient({ALL_PAIRS[0]: make_http_error(500), ALL_PAIRS[1]: make_http_error(429)})

    failures, stopped_early = run(client)

    assert (failures, stopped_early) == (2, True)
    assert client.calls == ALL_PAIRS[:2]


def test_network_error_counts_as_a_failure_and_the_other_calls_still_run(load, log):
    bad_pair = ALL_PAIRS[2]
    client = FakeClient({bad_pair: requests.ConnectionError("connection reset")})

    failures, stopped_early = run(client)

    assert (failures, stopped_early) == (1, False)
    assert client.calls == ALL_PAIRS
    call = log.for_pair(bad_pair)
    assert call["status_code"] is None
    assert call["error_message"] == "ConnectionError: connection reset"


def test_load_failure_counts_as_a_failure_and_the_other_calls_still_run(load, log):
    bad_pair = ALL_PAIRS[2]
    load.errors[bad_pair] = psycopg.errors.DataError("bad row")
    client = FakeClient()

    failures, stopped_early = run(client)

    assert (failures, stopped_early) == (1, False)
    assert client.calls == ALL_PAIRS
    assert log.pairs() == ALL_PAIRS
    assert log.for_pair(bad_pair)["error_message"] == "DataError: bad row"


def test_load_failure_is_logged_without_a_row_count(load, log):
    bad_pair = ALL_PAIRS[2]
    load.errors[bad_pair] = psycopg.errors.DataError("bad row")

    run(FakeClient())

    # The API call worked, so the status stays 200, but no rows were written.
    assert log.for_pair(bad_pair)["status_code"] == 200
    assert log.for_pair(bad_pair)["row_count"] is None


def test_values_from_a_failed_call_do_not_leak_into_the_next_log_row(load, log):
    bad_pair, next_pair = ALL_PAIRS[2], ALL_PAIRS[3]

    run(FakeClient({bad_pair: make_http_error(500, credits_left=3400)}))

    call = log.for_pair(next_pair)
    assert call["status_code"] == 200
    assert call["credits_left"] == 3500
    assert call["error_message"] is None


def test_database_outage_while_logging_stops_the_run(load, log):
    bad_pair = ALL_PAIRS[2]
    log.errors[bad_pair] = psycopg.OperationalError("server closed the connection")
    client = FakeClient()

    _, stopped_early = run(client)

    assert stopped_early is True
    assert client.calls == ALL_PAIRS[:3]


def test_database_outage_message_does_not_blame_the_api(load, log, capsys):
    log.errors[ALL_PAIRS[2]] = psycopg.OperationalError("server closed the connection")

    run(FakeClient())

    output = capsys.readouterr().out
    assert "could not write to api_runs" in output
    assert "HTTP" not in output


def test_stop_status_message_names_the_status(load, log, capsys):
    run(FakeClient({ALL_PAIRS[2]: make_http_error(429)}))

    assert "HTTP 429 will affect all remaining calls" in capsys.readouterr().out


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def run_main(load, log, monkeypatch):
    """Runs main() over two days with a fake client, without a database or arguments."""

    def _run_main(client):
        monkeypatch.setattr(main, "parse_args", lambda: None)
        monkeypatch.setattr(main, "get_query_dates", lambda args: [QUERY_DATE, date(2026, 9, 16)])
        monkeypatch.setattr(main, "get_connection", FakeConnection)
        monkeypatch.setattr(main, "OpenSkyClient", lambda: client)
        main.main()

    return _run_main


def test_main_exits_normally_when_every_call_succeeds(run_main):
    client = FakeClient()

    run_main(client)

    assert len(client.calls) == 2 * len(ALL_PAIRS)


def test_main_exits_with_1_when_a_call_fails(run_main):
    client = FakeClient({ALL_PAIRS[2]: make_http_error(500)})

    with pytest.raises(SystemExit) as exc_info:
        run_main(client)

    assert exc_info.value.code == 1


def test_main_exits_with_1_and_skips_later_days_when_logging_fails(run_main, log):
    # No API call fails here, so only the early stop can trigger the exit code.
    log.errors[ALL_PAIRS[0]] = psycopg.OperationalError("server closed the connection")
    client = FakeClient()

    with pytest.raises(SystemExit) as exc_info:
        run_main(client)

    assert exc_info.value.code == 1
    assert client.calls == ALL_PAIRS[:1]
