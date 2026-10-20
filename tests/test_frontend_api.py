"""The frontend's handling of a rate-limited response.

"Wait a moment" gave no way to tell a two-second pause from a minute-long
one, so the natural response was to keep clicking - which is what spent
the allowance to begin with.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontendv2")))

# The frontend's config module reads Streamlit secrets, so importing the
# client needs Streamlit present. It is installed in CI; skip rather than
# error for anyone running with the API's dependencies alone.
pytest.importorskip("streamlit")

import api  # noqa: E402


class FakeResponse:
    def __init__(self, headers=None):
        self.headers = headers or {}


def test_seconds_are_reported_as_seconds():
    message = api._rate_limited_message(FakeResponse({"Retry-After": "12"}))

    assert "12 seconds" in message


def test_one_second_is_not_pluralised():
    assert "1 second." in api._rate_limited_message(FakeResponse({"Retry-After": "1"}))


def test_longer_waits_are_rounded_up_to_minutes():
    message = api._rate_limited_message(FakeResponse({"Retry-After": "61"}))

    assert "2 minutes" in message


def test_a_missing_or_unparsable_header_still_reads_sensibly():
    for headers in ({}, {"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}):
        message = api._rate_limited_message(FakeResponse(headers))

        assert "Too many attempts" in message
        assert "second" not in message and "minute" not in message


def test_the_visitor_lookup_is_silent_outside_a_script_run():
    """It runs on every request, so it must never be the thing that
    raises."""

    assert api._visitor_address() == ""


# ------------------------------------------------------- backend URL


def test_a_bare_host_gets_https():
    """Render's fromService reference yields a hostname with no scheme,
    and requests rejects that outright."""

    import config

    assert config._normalise_url("medassist-api.onrender.com") == (
        "https://medassist-api.onrender.com"
    )


def test_a_full_url_is_left_alone():
    import config

    assert config._normalise_url("https://example.com/") == "https://example.com"
    assert config._normalise_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"


def test_local_addresses_stay_on_http():
    import config

    assert config._normalise_url("localhost:8000") == "http://localhost:8000"
    assert config._normalise_url("127.0.0.1:8000") == "http://127.0.0.1:8000"


def test_an_empty_setting_stays_empty():
    import config

    assert config._normalise_url("") == ""


# ------------------------------------------------- sign-up pre-check


def test_a_short_password_is_caught_before_any_network_call():
    """It used to cost a round trip - 30-60s when the API was asleep."""

    from components.auth_gate import registration_problem

    with patch_request() as request:
        problem = registration_problem("valid_name", "short", "short")

    assert "at least" in problem
    request.assert_not_called()


def test_the_sign_up_rules_match_the_server():
    from components.auth_gate import registration_problem

    assert registration_problem("", "long enough pw", "long enough pw")
    assert registration_problem("ab", "long enough pw", "long enough pw")  # too short
    assert registration_problem("-bad", "long enough pw", "long enough pw")  # bad start
    assert registration_problem("has space", "long enough pw", "long enough pw")
    assert registration_problem("valid_name", "          ", "          ")  # whitespace
    assert registration_problem("valid_name", "long enough pw", "different pw!") == (
        "The two passwords do not match."
    )
    assert registration_problem("Valid.Name-1", "long enough pw", "long enough pw") is None


def patch_request():
    from unittest.mock import patch

    return patch("api.requests.request")


# ------------------------------------------------- cold starts


def _conn_error():
    import requests

    return requests.ConnectionError("connection refused")


def _timeout():
    import requests

    return requests.Timeout("read timed out")


def test_a_safe_call_is_retried_once_when_the_api_is_asleep():
    """The free instance takes 30-60s to start; the first call after an
    idle spell is refused and looked like a broken deployment."""

    from unittest.mock import MagicMock, patch

    ok = MagicMock(status_code=200, ok=True)
    ok.json.return_value = {"fine": True}

    with (
        patch("api.requests.request", side_effect=[_conn_error(), ok]) as request,
        patch("api.wake_backend") as wake,
        patch("api.time.sleep"),
    ):
        assert api._request("GET", "/sessions").json() == {"fine": True}

    assert request.call_count == 2
    wake.assert_called_once()


def test_the_retry_gets_longer_to_wait_than_the_first_try():
    from unittest.mock import MagicMock, patch

    ok = MagicMock(status_code=200, ok=True)

    with (
        patch("api.requests.request", side_effect=[_timeout(), ok]) as request,
        patch("api.wake_backend"),
        patch("api.time.sleep"),
    ):
        api._request("GET", "/sessions")

    first = request.call_args_list[0].kwargs["timeout"][1]
    second = request.call_args_list[1].kwargs["timeout"][1]
    assert second > first


def test_a_write_is_never_repeated():
    """Re-sending an upload or a chat turn would double it."""

    from unittest.mock import patch

    with (
        patch("api.requests.request", side_effect=_conn_error()) as request,
        patch("api.wake_backend") as wake,
        patch("api.time.sleep"),
        pytest.raises(api.ApiError),
    ):
        api._request("POST", "/chat", json={"query": "hi"})

    assert request.call_count == 1
    wake.assert_not_called()


def test_the_message_says_the_api_is_waking_rather_than_broken():
    from unittest.mock import patch

    with (
        patch("api.requests.request", side_effect=_timeout()),
        patch("api.wake_backend"),
        patch("api.time.sleep"),
        pytest.raises(api.ApiError) as raised,
    ):
        api._request("POST", "/chat", json={"query": "hi"})

    message = str(raised.value)
    assert "waking up" in message
    assert "Is the backend running?" not in message
