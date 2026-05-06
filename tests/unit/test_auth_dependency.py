import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.auth import get_current_user
from app.core.exceptions import UnauthorizedError
from app.models.user import User


def make_credentials(token: str = "fake.jwt.token") -> MagicMock:
    cred = MagicMock()
    cred.credentials = token
    return cred


def make_session(user: MagicMock | None) -> AsyncMock:
    session = AsyncMock()
    session.get.return_value = user
    return session


def make_valid_payload(user_id: uuid.UUID) -> dict:
    return {"type": "access", "sub": str(user_id)}


@pytest.fixture
def mock_settings():
    with patch("app.core.auth.get_settings") as m:
        m.return_value = MagicMock(secret_key="test-secret", algorithm="HS256")
        yield m


class TestGetCurrentUser:
    async def test_returns_user_for_valid_token(self, mock_settings) -> None:
        user_id = uuid.uuid4()
        mock_user = MagicMock(spec=User, is_active=True)

        payload = make_valid_payload(user_id)
        with patch("app.core.auth.jwt.decode", return_value=payload):
            result = await get_current_user(
                credentials=make_credentials(),
                session=make_session(mock_user),
            )

        assert result is mock_user

    async def test_raises_on_expired_token(self, mock_settings) -> None:
        import jwt as pyjwt

        with patch("app.core.auth.jwt.decode", side_effect=pyjwt.ExpiredSignatureError):
            with pytest.raises(UnauthorizedError, match="Token has expired"):
                await get_current_user(
                    credentials=make_credentials(),
                    session=make_session(None),
                )

    async def test_raises_on_invalid_token(self, mock_settings) -> None:
        import jwt as pyjwt

        with patch("app.core.auth.jwt.decode", side_effect=pyjwt.InvalidTokenError):
            with pytest.raises(UnauthorizedError, match="Invalid token"):
                await get_current_user(
                    credentials=make_credentials(),
                    session=make_session(None),
                )

    async def test_raises_on_wrong_token_type(self, mock_settings) -> None:
        payload = {"type": "refresh", "sub": str(uuid.uuid4())}

        with patch("app.core.auth.jwt.decode", return_value=payload):
            with pytest.raises(UnauthorizedError, match="Invalid token type"):
                await get_current_user(
                    credentials=make_credentials(),
                    session=make_session(None),
                )

    async def test_raises_when_user_not_found(self, mock_settings) -> None:
        user_id = uuid.uuid4()

        payload = make_valid_payload(user_id)
        with patch("app.core.auth.jwt.decode", return_value=payload):
            with pytest.raises(UnauthorizedError, match="not found or inactive"):
                await get_current_user(
                    credentials=make_credentials(),
                    session=make_session(None),
                )

    async def test_raises_when_user_inactive(self, mock_settings) -> None:
        user_id = uuid.uuid4()
        inactive_user = MagicMock(spec=User, is_active=False)

        payload = make_valid_payload(user_id)
        with patch("app.core.auth.jwt.decode", return_value=payload):
            with pytest.raises(UnauthorizedError, match="not found or inactive"):
                await get_current_user(
                    credentials=make_credentials(),
                    session=make_session(inactive_user),
                )
