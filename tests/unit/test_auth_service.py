import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt
import jwt
import pytest

from app.core.config import Settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.models.user import User
from app.schemas.user import RefreshTokenRequest, UserCreate, UserLogin
from app.services.auth import AuthService

TEST_SECRET = "test-secret-key-for-unit-tests-only-32chars"
TEST_EMAIL = "user@example.com"
TEST_PASSWORD = "password123"


def make_mock_user(
    email: str = TEST_EMAIL,
    password: str = TEST_PASSWORD,
    is_active: bool = True,
) -> MagicMock:
    """Build a mock User object for tests without touching the DB."""
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = email
    user.hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user.is_active = is_active
    user.is_verified = False
    user.created_at = datetime.now(UTC)
    return user


def make_refresh_token(user_id: uuid.UUID, secret: str, expired: bool = False) -> str:
    """Create a real JWT refresh token for test inputs."""
    exp = datetime.now(UTC) + (
        timedelta(seconds=-1) if expired else timedelta(days=7)
    )
    return jwt.encode(
        {"sub": str(user_id), "type": "refresh", "exp": exp},
        secret,
        algorithm="HS256",
    )


@pytest.fixture
def mock_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_repo: AsyncMock, test_settings: Settings) -> AuthService:
    with patch("app.services.auth.get_settings", return_value=test_settings):
        yield AuthService(mock_repo)


class TestRegister:
    async def test_success_creates_user(
        self, service: AuthService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.find_by_email.return_value = None
        mock_repo.create.return_value = make_mock_user()

        user = await service.register(
            UserCreate(email=TEST_EMAIL, password=TEST_PASSWORD)
        )

        mock_repo.find_by_email.assert_called_once_with(TEST_EMAIL)
        assert user.email == TEST_EMAIL

    async def test_success_stores_hashed_password(
        self, service: AuthService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.find_by_email.return_value = None
        mock_repo.create.return_value = make_mock_user()

        await service.register(UserCreate(email=TEST_EMAIL, password=TEST_PASSWORD))

        _, call_kwargs = mock_repo.create.call_args
        hashed = mock_repo.create.call_args[0][1]
        assert bcrypt.checkpw(TEST_PASSWORD.encode(), hashed.encode())

    async def test_duplicate_email_raises_conflict(
        self, service: AuthService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.find_by_email.return_value = make_mock_user()

        with pytest.raises(ConflictError, match="Email already registered"):
            await service.register(
                UserCreate(email=TEST_EMAIL, password=TEST_PASSWORD)
            )

        mock_repo.create.assert_not_called()


class TestLogin:
    async def test_success_returns_token_pair(
        self, service: AuthService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.find_by_email.return_value = make_mock_user()

        tokens = await service.login(
            UserLogin(email=TEST_EMAIL, password=TEST_PASSWORD)
        )

        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.token_type == "bearer"

    async def test_wrong_password_raises_unauthorized(
        self, service: AuthService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.find_by_email.return_value = make_mock_user()

        with pytest.raises(UnauthorizedError, match="Invalid email or password"):
            await service.login(
                UserLogin(email=TEST_EMAIL, password="wrongpassword")
            )

    async def test_unknown_email_raises_unauthorized(
        self, service: AuthService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.find_by_email.return_value = None

        with pytest.raises(UnauthorizedError, match="Invalid email or password"):
            await service.login(
                UserLogin(email="nobody@example.com", password=TEST_PASSWORD)
            )

    async def test_inactive_user_raises_forbidden(
        self, service: AuthService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.find_by_email.return_value = make_mock_user(is_active=False)

        with pytest.raises(ForbiddenError, match="Account is inactive"):
            await service.login(
                UserLogin(email=TEST_EMAIL, password=TEST_PASSWORD)
            )


class TestRefresh:
    async def test_success_returns_new_token_pair(
        self, service: AuthService, mock_repo: AsyncMock
    ) -> None:
        user = make_mock_user()
        mock_repo.find_by_id.return_value = user
        token = make_refresh_token(user.id, TEST_SECRET)

        tokens = await service.refresh(RefreshTokenRequest(refresh_token=token))

        assert tokens.access_token
        assert tokens.refresh_token

    async def test_expired_token_raises_unauthorized(
        self, service: AuthService, mock_repo: AsyncMock
    ) -> None:
        token = make_refresh_token(uuid.uuid4(), TEST_SECRET, expired=True)

        with pytest.raises(UnauthorizedError, match="Token has expired"):
            await service.refresh(RefreshTokenRequest(refresh_token=token))

    async def test_invalid_token_raises_unauthorized(
        self, service: AuthService, mock_repo: AsyncMock
    ) -> None:
        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await service.refresh(
                RefreshTokenRequest(refresh_token="not.a.valid.jwt")
            )

    async def test_access_token_rejected_as_refresh(
        self, service: AuthService, mock_repo: AsyncMock
    ) -> None:
        access_token = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "type": "access",
                "exp": datetime.now(UTC) + timedelta(minutes=15),
            },
            TEST_SECRET,
            algorithm="HS256",
        )

        with pytest.raises(UnauthorizedError, match="Invalid token type"):
            await service.refresh(RefreshTokenRequest(refresh_token=access_token))

    async def test_deleted_user_raises_unauthorized(
        self, service: AuthService, mock_repo: AsyncMock
    ) -> None:
        user_id = uuid.uuid4()
        mock_repo.find_by_id.return_value = None
        token = make_refresh_token(user_id, TEST_SECRET)

        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await service.refresh(RefreshTokenRequest(refresh_token=token))
