import argparse
from argparse import Namespace
from datetime import date

import pytest

from ingestion import main
from ingestion.main import get_query_dates, validate_and_fill_args

YESTERDAY = date(2026, 10, 15)


@pytest.fixture(autouse=True)
def fixed_yesterday(monkeypatch):
    # Pin the clock so these tests give the same result on any day.
    monkeypatch.setattr(main, "yesterday_utc", lambda: YESTERDAY)


def make_args(date=None, start=None, end=None, days=None):
    return Namespace(date=date, start=start, end=end, days=days)


def test_start_and_end_are_inclusive():
    args = make_args(start=date(2026, 9, 1), end=date(2026, 9, 3))

    result = get_query_dates(args)

    assert result == [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)]

def test_date_gives_one_date():
    args = make_args(date=date(2026, 9, 15))

    result = get_query_dates(args)

    assert result == [date(2026, 9, 15)]


def test_start_equal_to_end_gives_one_date():
    args = make_args(start=date(2026, 9, 15), end=date(2026, 9, 15))

    result = get_query_dates(args)

    assert result == [date(2026, 9, 15)]


def test_range_crosses_month_end():
    args = make_args(start=date(2026, 9, 30), end=date(2026, 10, 2))

    result = get_query_dates(args)

    assert result == [date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)]


def test_days_gives_last_n_days_ending_yesterday():
    args = make_args(days=3)

    result = get_query_dates(args)

    assert result == [date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 15)]


def test_days_can_cross_a_month_end(monkeypatch):
    monkeypatch.setattr(main, "yesterday_utc", lambda: date(2026, 10, 1))
    args = make_args(days=2)

    result = get_query_dates(args)

    assert result == [date(2026, 9, 30), date(2026, 10, 1)]


def test_no_arguments_gives_yesterday():
    args = make_args()

    result = get_query_dates(args)

    assert result == [YESTERDAY]


@pytest.mark.parametrize(
    "args, message",
    [
        (make_args(end=date(2026, 9, 3)), "--end requires --start"),
        (make_args(start=date(2026, 9, 3), end=date(2026, 9, 1)), "--start cannot be after --end"),
        (make_args(date=date(2026, 10, 16)), "--date must be 2026-10-15 or earlier"),
        (make_args(date=date(2026, 12, 25)), "--date must be 2026-10-15 or earlier"),
        (make_args(start=date(2026, 10, 16)), "--start must be 2026-10-15 or earlier"),
        (make_args(start=date(2026, 9, 1), end=date(2026, 10, 16)), "--end must be 2026-10-15 or earlier"),
        (make_args(days=0), "--days must be at least 1"),
        (make_args(days=-1), "--days must be at least 1"),
    ],
)
def test_invalid_arguments_exit_with_an_error(args, message, capsys):
    with pytest.raises(SystemExit) as exc_info:
        validate_and_fill_args(argparse.ArgumentParser(), args)

    # Checking the message proves it exited for this reason and not another one.
    assert exc_info.value.code == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize(
    "args",
    [
        make_args(date=YESTERDAY),
        make_args(start=YESTERDAY, end=YESTERDAY),
        make_args(days=1),
        make_args(),
    ],
)
def test_valid_arguments_are_accepted(args):
    validate_and_fill_args(argparse.ArgumentParser(), args)


def test_end_defaults_to_yesterday():
    args = make_args(start=date(2026, 9, 1))

    validate_and_fill_args(argparse.ArgumentParser(), args)

    assert args.end == YESTERDAY


def test_end_is_kept_when_given():
    args = make_args(start=date(2026, 9, 1), end=date(2026, 9, 3))

    validate_and_fill_args(argparse.ArgumentParser(), args)

    assert args.end == date(2026, 9, 3)
