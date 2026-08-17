import os
import sys

# Fallback for running pytest without installing the project (`pip install -e .`).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Settings are validated at import, so the required values must exist
# before any app module is imported. Everything network-facing is mocked
# in the tests themselves, so dummy values are fine.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("GROQ_API_KEY", "test-dummy-key-for-ci")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("API_KEYS", "")


import pytest  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _create_schema():
    from app.session.db import init_db

    init_db()
