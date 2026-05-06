import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import RefreshTokenRequest, TokenResponse, UserCreate, UserLogin


class AuthService:
    """Handles user registration, login, and JWT token lifecycle."""

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo
        self._settings = get_settings()

    async def register(self, data: UserCreate) -> User:
        """Register a new user.

        Args:
            data: Validated registration payload.

        Returns:
            The newly created User.

        Raises:
            ConflictError: If the email is already registered.
        """
        existing = await self.user_repo.find_by_email(data.email)
        if existing:
            raise ConflictError("Email already registered")
        hashed = self._hash_password(data.password)
        return await self.user_repo.create(data.email, hashed)

    async def login(self, data: UserLogin) -> TokenResponse:
        """Authenticate a user and return a JWT token pair.

        Args:
            data: Login credentials.

        Returns:
            Access and refresh tokens.

        Raises:
            UnauthorizedError: If credentials are invalid.
            ForbiddenError: If the account is inactive.
        """
        user = await self.user_repo.find_by_email(data.email)
        if not user or not self._verify_password(data.password, user.hashed_password):
            raise UnauthorizedError("Invalid email or password")
        if not user.is_active:
            raise ForbiddenError("Account is inactive")
        return self._create_token_pair(user.id)

    async def refresh(self, data: RefreshTokenRequest) -> TokenResponse:
        """Issue a new token pair from a valid refresh token.

        Args:
            data: Payload containing the refresh token.

        Returns:
            A new access and refresh token pair.

        Raises:
            UnauthorizedError: If the token is invalid or the user no longer exists.
        """
        user_id = self._decode_token(data.refresh_token, expected_type="refresh")
        user = await self.user_repo.find_by_id(user_id)
        if not user or not user.is_active:
            raise UnauthorizedError("Invalid token")
        return self._create_token_pair(user.id)

    def _hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def _verify_password(self, plain: str, hashed: str) -> bool:
        return bcrypt.checkpw(plain.encode(), hashed.encode())

    def _create_token_pair(self, user_id: uuid.UUID) -> TokenResponse:
        access_token = self._encode_token(
            {"sub": str(user_id), "type": "access"},
            timedelta(minutes=self._settings.access_token_expire_minutes),
        )
        refresh_token = self._encode_token(
            {"sub": str(user_id), "type": "refresh"},
            timedelta(days=self._settings.refresh_token_expire_days),
        )
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    def _encode_token(self, payload: dict[str, Any], expires_delta: timedelta) -> str:
        payload["exp"] = datetime.now(UTC) + expires_delta
        return jwt.encode(
            payload,
            self._settings.secret_key,
            algorithm=self._settings.algorithm,
        )

    def _decode_token(self, token: str, expected_type: str) -> uuid.UUID:
        """Decode and validate a JWT, returning the user UUID.

        Args:
            token: The raw JWT string.
            expected_type: Either "access" or "refresh".

        Returns:
            The user UUID from the token subject claim.

        Raises:
            UnauthorizedError: If the token is expired, malformed, or wrong type.
        """
        try:
            payload = jwt.decode(
                token,
                self._settings.secret_key,
                algorithms=[self._settings.algorithm],
            )
        except jwt.ExpiredSignatureError:
            raise UnauthorizedError("Token has expired")
        except jwt.InvalidTokenError:
            raise UnauthorizedError("Invalid token")

        if payload.get("type") != expected_type:
            raise UnauthorizedError("Invalid token type")

        return uuid.UUID(payload["sub"])
