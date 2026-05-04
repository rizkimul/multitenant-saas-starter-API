import pytest

from app.core.config import Settings

TEST_SECRET = "test-secret-key-for-unit-tests-only-32chars"


@pytest.fixture
def test_settings() -> Settings:
    """Isolated Settings instance for tests — never reads from .env."""
    return Settings(
        postgres_user="test",
        postgres_password="test",
        postgres_db="test",
        secret_key=TEST_SECRET,
    )
