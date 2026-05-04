import uuid
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.exceptions import UnauthorizedError
from app.models.user import User
from app.repositories.user import UserRepository

_security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_security)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """FastAPI dependency that extracts and validates the Bearer token.

    Args:
        credentials: Authorization header parsed by HTTPBearer.
        session: Injected database session.

    Returns:
        The authenticated User object.

    Raises:
        UnauthorizedError: If the token is missing, invalid, or the user
            no longer exists.
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token has expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Invalid token")

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")

    user_id = uuid.UUID(payload["sub"])
    user = await UserRepository(session).find_by_id(user_id)

    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
