import os
from datetime import date
from uuid import uuid4

import psycopg
import pytest

from ingestion.load import get_connection, load_flights, log_api_run

# A slice that real data can never use, on top of the rollback in the fixture.
AIRPORT = "TEST"
DIRECTION = "arrival"
QUERY_DATE = date(1999, 1, 1)
RUN_ID = uuid4()
FLIGHTS = [{"icao24": "750541", "callsign": "MAS197  "}, {"icao24": "750542", "callsign": None}]


@pytest.fixture
def conn():
    # These tests need the real delete, insert and rollback, which a fake can't prove.
    try:
        connection = get_connection()
    except psycopg.OperationalError:
        # Skipping is fine on a laptop without `make up`, but CI must never skip these.
        if os.getenv("CI"):
            raise
        pytest.skip("Postgres isn't running")

    with connection:
        # Everything a test writes is rolled back, so this is safe on a real database.
        with connection.transaction(force_rollback=True):
            yield connection


def payloads(conn, airport=AIRPORT, direction=DIRECTION, query_date=QUERY_DATE):
    rows = conn.execute(
        """
        SELECT payload FROM raw.flights
        WHERE airport = %s AND direction = %s AND query_date = %s
        ORDER BY id
        """,
        (airport, direction, query_date),
    ).fetchall()
    return [row[0] for row in rows]


def load(conn, flights, airport=AIRPORT, direction=DIRECTION, query_date=QUERY_DATE, run_id=RUN_ID):
    return load_flights(conn, flights, airport, direction, query_date, run_id)


def test_load_stores_each_flight_untouched_and_returns_the_count(conn):
    assert load(conn, FLIGHTS) == 2

    assert payloads(conn) == FLIGHTS


def test_load_stores_the_run_id(conn):
    load(conn, FLIGHTS)

    run_ids = conn.execute("SELECT DISTINCT run_id FROM raw.flights WHERE airport = %s", (AIRPORT,)).fetchall()
    assert run_ids == [(RUN_ID,)]


def test_loading_the_same_slice_twice_replaces_it(conn):
    load(conn, FLIGHTS)
    load(conn, FLIGHTS[:1])

    assert payloads(conn) == FLIGHTS[:1]


def test_empty_result_clears_the_slice(conn):
    load(conn, FLIGHTS)

    assert load(conn, []) == 0

    assert payloads(conn) == []


@pytest.mark.parametrize(
    "other_slice",
    [
        {"airport": "TST2"},
        {"direction": "departure"},
        {"query_date": date(1999, 1, 2)},
    ],
)
def test_load_leaves_other_slices_alone(conn, other_slice):
    load(conn, FLIGHTS, **other_slice)

    load(conn, FLIGHTS[:1])

    assert payloads(conn, **other_slice) == FLIGHTS


def test_failed_insert_keeps_the_old_rows_and_the_connection_usable(conn):
    load(conn, FLIGHTS)

    # run_id is NOT NULL, so the insert fails after the delete has already run.
    with pytest.raises(psycopg.errors.NotNullViolation):
        load(conn, FLIGHTS[:1], run_id=None)

    assert payloads(conn) == FLIGHTS


def test_log_api_run_stores_a_successful_call(conn):
    log_api_run(conn, AIRPORT, DIRECTION, QUERY_DATE, RUN_ID, status_code=200, row_count=2, credits_left=3500)

    row = conn.execute(
        """
        SELECT direction, query_date, status_code, row_count, credits_left, error_message, run_id
        FROM raw.api_runs WHERE airport = %s
        """,
        (AIRPORT,),
    ).fetchall()
    assert row == [(DIRECTION, QUERY_DATE, 200, 2, 3500, None, RUN_ID)]


def test_log_api_run_stores_a_failed_call(conn):
    log_api_run(conn, AIRPORT, DIRECTION, QUERY_DATE, RUN_ID, error_message="connection reset")

    row = conn.execute(
        "SELECT status_code, row_count, credits_left, error_message FROM raw.api_runs WHERE airport = %s",
        (AIRPORT,),
    ).fetchall()
    assert row == [(None, None, None, "connection reset")]
