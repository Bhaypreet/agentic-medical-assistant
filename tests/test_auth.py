"""Accounts, passwords and tokens."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.auth import service
from app.config import settings

GOOD_PASSWORD = "correct horse battery"


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _name():
    return f"user{uuid.uuid4().hex[:10]}"


# ------------------------------------------------------------- hashing


def test_password_hash_is_salted_so_equal_passwords_differ():
    a, b = service.new_salt(), service.new_salt()
    assert service.hash_password(GOOD_PASSWORD, a) != service.hash_password(GOOD_PASSWORD, b)


def test_password_verifies_against_its_own_salt():
    salt = service.new_salt()
    stored = service.hash_password(GOOD_PASSWORD, salt)

    assert service.verify_password(GOOD_PASSWORD, salt, stored)
    assert not service.verify_password("wrong password entirely", salt, stored)


def test_the_plaintext_password_is_never_stored():
    from sqlalchemy import select

    from app.session.db import SessionLocal, User

    username = _name()
    service.register(username, GOOD_PASSWORD)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))

    assert GOOD_PASSWORD not in user.password_hash
    assert GOOD_PASSWORD not in user.password_salt


def test_only_a_token_hash_is_stored():
    from sqlalchemy import select

    from app.session.db import AuthToken, SessionLocal

    username = _name()
    service.register(username, GOOD_PASSWORD)
    _, token, _ = service.authenticate(username, GOOD_PASSWORD)

    with SessionLocal() as db:
        rows = list(db.scalars(select(AuthToken)))

    assert all(row.token_hash != token for row in rows)


# -------------------------------------------------------- registration


def test_register_then_sign_in(client):
    username = _name()

    created = client.post("/auth/register", json={"username": username, "password": GOOD_PASSWORD})
    assert created.status_code == 201
    assert created.json()["access_token"]

    signed_in = client.post("/auth/login", json={"username": username, "password": GOOD_PASSWORD})
    assert signed_in.status_code == 200
    assert signed_in.json()["username"] == username


def test_usernames_are_case_insensitive(client):
    username = _name()
    client.post("/auth/register", json={"username": username, "password": GOOD_PASSWORD})

    taken = client.post(
        "/auth/register", json={"username": username.upper(), "password": GOOD_PASSWORD}
    )
    assert taken.status_code == 400

    ok = client.post("/auth/login", json={"username": username.upper(), "password": GOOD_PASSWORD})
    assert ok.status_code == 200


@pytest.mark.parametrize("username", ["ab", "-starts-with-dash", "has space", "x" * 40, ""])
def test_invalid_usernames_are_refused(client, username):
    response = client.post("/auth/register", json={"username": username, "password": GOOD_PASSWORD})
    assert response.status_code in (400, 422)


def test_short_passwords_are_refused(client):
    response = client.post("/auth/register", json={"username": _name(), "password": "short"})
    assert response.status_code == 400
    assert "at least" in response.json()["detail"]


def test_registration_can_be_closed(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_registration", False)

    response = client.post("/auth/register", json={"username": _name(), "password": GOOD_PASSWORD})
    assert response.status_code == 400


# ---------------------------------------------------------------- login


def test_wrong_password_is_rejected(client):
    username = _name()
    client.post("/auth/register", json={"username": username, "password": GOOD_PASSWORD})

    response = client.post(
        "/auth/login", json={"username": username, "password": "not the password"}
    )
    assert response.status_code == 401


def test_unknown_user_and_wrong_password_look_identical(client):
    username = _name()
    client.post("/auth/register", json={"username": username, "password": GOOD_PASSWORD})

    wrong = client.post("/auth/login", json={"username": username, "password": "nope nope nope"})
    missing = client.post("/auth/login", json={"username": _name(), "password": "nope nope nope"})

    # Responses must not reveal whether the account exists.
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["detail"] == missing.json()["detail"]


# --------------------------------------------------------------- tokens


def test_token_authenticates_a_data_endpoint(client):
    username = _name()
    token = client.post(
        "/auth/register", json={"username": username, "password": GOOD_PASSWORD}
    ).json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == username
    assert me.json()["is_service_account"] is False


def test_logout_revokes_the_token(client):
    username = _name()
    token = client.post(
        "/auth/register", json={"username": username, "password": GOOD_PASSWORD}
    ).json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}

    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_expired_tokens_are_refused(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_token_ttl_hours", -1)

    username = _name()
    service.register(username, GOOD_PASSWORD)
    _, token, _ = service.authenticate(username, GOOD_PASSWORD)

    assert service.principal_for_token(token) is None


def test_changing_a_password_invalidates_existing_sessions(client):
    username = _name()
    token = client.post(
        "/auth/register", json={"username": username, "password": GOOD_PASSWORD}
    ).json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}

    changed = client.post(
        "/auth/change-password",
        json={"current_password": GOOD_PASSWORD, "new_password": "a whole new password"},
        headers=headers,
    )
    assert changed.status_code == 204

    # The old token must stop working.
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert (
        client.post(
            "/auth/login", json={"username": username, "password": "a whole new password"}
        ).status_code
        == 200
    )


def test_expired_tokens_are_purged():
    username = _name()
    service.register(username, GOOD_PASSWORD)
    _, token, _ = service.authenticate(username, GOOD_PASSWORD)

    service.revoke_token(token)

    assert service.purge_expired_tokens() >= 1


# ------------------------------------------------------------ isolation


def test_two_users_cannot_see_each_others_chats(client):
    """The reason this feature exists: two people using the same
    deployment previously shared one owner and one chat list."""

    from unittest.mock import patch

    session_id = str(uuid.uuid4())

    alice = {
        "Authorization": "Bearer "
        + client.post(
            "/auth/register", json={"username": _name(), "password": GOOD_PASSWORD}
        ).json()["access_token"]
    }
    bob = {
        "Authorization": "Bearer "
        + client.post(
            "/auth/register", json={"username": _name(), "password": GOOD_PASSWORD}
        ).json()["access_token"]
    }

    with (
        patch(
            "app.api.routes.graph.invoke",
            return_value={"response": "Your haemoglobin is low.", "severity": 1},
        ),
        patch("app.api.routes.generate_suggestions", return_value=[]),
    ):
        client.post(
            "/chat",
            json={"query": "explain my report", "session_id": session_id},
            headers=alice,
        )

    assert (
        len(client.get(f"/history?session_id={session_id}", headers=alice).json()["messages"]) == 2
    )
    assert client.get(f"/history?session_id={session_id}", headers=bob).json()["messages"] == []

    assert client.get("/sessions", headers=bob).json() == []
