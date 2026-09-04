"""Accounts, passwords and sign-in tokens.

Design notes, since these are the decisions that matter:

* Passwords are hashed with scrypt from the standard library. It is
  memory-hard, so it resists GPU cracking the way bcrypt/argon2 do, and
  it avoids adding a native dependency that has to compile on every
  deployment target. Each password gets a random 16-byte salt, plus a
  server-side pepper from SECRET_KEY so a stolen database alone is not
  enough to mount an offline attack.

* Sign-in tokens are opaque random strings. Only their SHA-256 hash is
  stored, so a database leak does not hand over live sessions, and rows
  can be revoked - which a stateless JWT cannot be without building the
  revocation list a token table already is.

* Login never reveals whether a username exists. An unknown user still
  pays the cost of a hash comparison against a dummy value, so response
  timing does not leak account existence either.
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import settings
from app.logging_config import get_logger
from app.session.db import AuthToken, SessionLocal, User, utcnow

logger = get_logger(__name__)

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}

# Compared against when the username is unknown, so that path costs the
# same as a real verification.
_DUMMY_SALT = "0" * 32
_DUMMY_HASH = "0" * 64


class AuthError(Exception):
    """Sign-in or registration was refused. The message is user-facing."""


@dataclass(frozen=True)
class Principal:
    """The authenticated caller."""

    owner: str
    user_id: int | None = None
    username: str = ""

    @property
    def is_machine(self) -> bool:
        return self.user_id is None


# ---------------------------------------------------------------- hashing


def _pepper() -> bytes:
    return settings.secret_key.encode("utf-8")


def hash_password(password: str, salt: str) -> str:
    derived = hashlib.scrypt(
        password.encode("utf-8") + _pepper(),
        salt=bytes.fromhex(salt),
        **_SCRYPT,
    )
    return derived.hex()


def new_salt() -> str:
    return secrets.token_hex(16)


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    try:
        candidate = hash_password(password, salt)
    except ValueError:
        return False

    return hmac.compare_digest(candidate, expected_hash)


def _hash_token(token: str) -> str:
    """Tokens are high-entropy already, so a plain digest is sufficient."""
    return hashlib.sha256(token.encode("utf-8") + _pepper()).hexdigest()


# ---------------------------------------------------------- validation


def normalise_username(username: str) -> str:
    return (username or "").strip().lower()


def validate_username(username: str) -> str:
    cleaned = normalise_username(username)

    if not USERNAME_PATTERN.match(cleaned):
        raise AuthError(
            "Username must be 3-32 characters, start with a letter or number, "
            "and use only letters, numbers, dots, hyphens or underscores."
        )

    return cleaned


def validate_password(password: str) -> str:
    password = password or ""

    if len(password) < settings.min_password_length:
        raise AuthError(f"Password must be at least {settings.min_password_length} characters.")

    if len(password) > settings.max_password_length:
        raise AuthError(f"Password must be at most {settings.max_password_length} characters.")

    if password.strip() == "":
        raise AuthError("Password cannot be only whitespace.")

    return password


# ------------------------------------------------------------- accounts


def register(username: str, password: str, display_name: str = "") -> Principal:
    if not settings.allow_registration:
        raise AuthError("Registration is closed on this deployment.")

    username = validate_username(username)
    validate_password(password)

    salt = new_salt()

    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)) is not None:
            raise AuthError("That username is already taken.")

        user = User(
            username=username,
            display_name=(display_name or username).strip()[:64],
            password_salt=salt,
            password_hash=hash_password(password, salt),
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        logger.info("Account created", extra={"user_id": user.id})

        return Principal(owner=user.owner_key, user_id=user.id, username=user.username)


def authenticate(username: str, password: str) -> tuple[Principal, str, datetime]:
    """Verify credentials and issue a token. Returns (principal, token, expiry)."""

    username = normalise_username(username)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))

        # Always run a comparison so an unknown username costs the same
        # as a wrong password.
        if user is None:
            verify_password(password, _DUMMY_SALT, _DUMMY_HASH)
            raise AuthError("Incorrect username or password.")

        if not verify_password(password, user.password_salt, user.password_hash):
            logger.warning("Failed sign-in", extra={"user_id": user.id})
            raise AuthError("Incorrect username or password.")

        if not user.is_active:
            raise AuthError("This account has been disabled.")

        token = secrets.token_urlsafe(32)
        expires_at = utcnow() + timedelta(hours=settings.auth_token_ttl_hours)

        db.add(
            AuthToken(
                token_hash=_hash_token(token),
                user_id=user.id,
                expires_at=expires_at,
            )
        )

        user.last_login_at = utcnow()
        db.commit()

        logger.info("Signed in", extra={"user_id": user.id})

        return (
            Principal(owner=user.owner_key, user_id=user.id, username=user.username),
            token,
            expires_at,
        )


def principal_for_token(token: str) -> Principal | None:
    """Resolve a bearer token, or None if it is unknown, revoked or expired."""

    if not token:
        return None

    with SessionLocal() as db:
        row = db.scalar(select(AuthToken).where(AuthToken.token_hash == _hash_token(token)))

        if row is None or row.revoked:
            return None

        expires = row.expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)

        if expires is not None and expires < utcnow():
            return None

        user = db.get(User, row.user_id)

        if user is None or not user.is_active:
            return None

        return Principal(owner=user.owner_key, user_id=user.id, username=user.username)


def revoke_token(token: str) -> bool:
    with SessionLocal() as db:
        row = db.scalar(select(AuthToken).where(AuthToken.token_hash == _hash_token(token)))

        if row is None:
            return False

        row.revoked = True
        db.commit()

        return True


def change_password(user_id: int, current_password: str, new_password: str) -> None:
    validate_password(new_password)

    with SessionLocal() as db:
        user = db.get(User, user_id)

        if user is None:
            raise AuthError("Account not found.")

        if not verify_password(current_password, user.password_salt, user.password_hash):
            raise AuthError("Current password is incorrect.")

        user.password_salt = new_salt()
        user.password_hash = hash_password(new_password, user.password_salt)

        # Every existing session is invalidated - a password change must
        # log out anyone holding an old token.
        for row in db.scalars(select(AuthToken).where(AuthToken.user_id == user_id)):
            row.revoked = True

        db.commit()

        logger.info("Password changed", extra={"user_id": user_id})


def purge_expired_tokens() -> int:
    """Remove tokens that can no longer authenticate anything."""

    from sqlalchemy import delete, or_

    with SessionLocal() as db:
        result = db.execute(
            delete(AuthToken).where(
                or_(AuthToken.expires_at < utcnow(), AuthToken.revoked.is_(True))
            )
        )
        db.commit()

        return result.rowcount or 0
