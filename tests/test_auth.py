from datetime import datetime, timedelta

import pytest
import requests

from ingestion import auth
from ingestion.auth import TOKEN_REFRESH_MARGIN, TokenManager
from ingestion.config import CLIENT_ID, CLIENT_SECRET, REQUEST_TIMEOUT, TOKEN_URL

NOW = datetime(2026, 9, 15, 12, 0, 0)


class FakeClock:
    """Stands in for datetime in auth.py, so a test can move time forward."""

    def __init__(self):
        self.current = NOW

    def now(self):
        return self.current


class FakePost:
    """Stands in for requests.post: returns the next response and records each call."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def make_response(status_code=200, **body):
    response = requests.Response()
    response.status_code = status_code
    response.json = lambda: body
    return response


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(auth, "datetime", fake)
    return fake


def use_post(monkeypatch, *responses):
    fake = FakePost(*responses)
    monkeypatch.setattr(auth.requests, "post", fake)
    return fake


def test_first_call_asks_for_a_token_with_the_client_credentials(monkeypatch, clock):
    post = use_post(monkeypatch, make_response(access_token="abc", expires_in=1800))

    assert TokenManager().get_token() == "abc"

    assert post.calls == [{
        "url": TOKEN_URL,
        "data": {
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        "timeout": REQUEST_TIMEOUT,
    }]


def test_valid_token_is_reused(monkeypatch, clock):
    post = use_post(monkeypatch, make_response(access_token="abc", expires_in=1800))
    manager = TokenManager()

    manager.get_token()
    clock.current = NOW + timedelta(seconds=60)

    assert manager.get_token() == "abc"
    assert len(post.calls) == 1


def test_token_is_refreshed_early_by_the_margin(monkeypatch, clock):
    post = use_post(
        monkeypatch,
        make_response(access_token="old", expires_in=1800),
        make_response(access_token="new", expires_in=1800),
    )
    manager = TokenManager()
    manager.get_token()

    # One second before the margin starts, the old token is still used.
    clock.current = NOW + timedelta(seconds=1800 - TOKEN_REFRESH_MARGIN - 1)
    assert manager.get_token() == "old"

    # Once the margin starts, it's replaced even though the server would still accept it.
    clock.current = NOW + timedelta(seconds=1800 - TOKEN_REFRESH_MARGIN)
    assert manager.get_token() == "new"
    assert len(post.calls) == 2


def test_missing_expires_in_defaults_to_30_minutes(monkeypatch, clock):
    use_post(monkeypatch, make_response(access_token="abc"))
    manager = TokenManager()

    manager.get_token()

    assert manager.expires_at == NOW + timedelta(seconds=1800 - TOKEN_REFRESH_MARGIN)


def test_failed_refresh_raises_and_stores_no_token(monkeypatch, clock):
    use_post(monkeypatch, make_response(status_code=401))
    manager = TokenManager()

    with pytest.raises(requests.HTTPError):
        manager.get_token()

    assert manager.token is None


def test_failed_refresh_can_be_retried(monkeypatch, clock):
    use_post(monkeypatch, make_response(status_code=500), make_response(access_token="abc", expires_in=1800))
    manager = TokenManager()

    with pytest.raises(requests.HTTPError):
        manager.get_token()

    assert manager.get_token() == "abc"


def test_headers_carry_the_bearer_token(monkeypatch, clock):
    use_post(monkeypatch, make_response(access_token="abc", expires_in=1800))

    assert TokenManager().headers() == {"Authorization": "Bearer abc"}
