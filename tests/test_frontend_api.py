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
