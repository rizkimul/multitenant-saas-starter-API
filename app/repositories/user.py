import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Data access layer for the users table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_email(self, email: str) -> User | None:
        """Fetch a user by email address.

        Args:
            email: The email address to search for.

        Returns:
            The matching User, or None if not found.
        """
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalars().first()

    async def find_by_id(self, user_id: uuid.UUID) -> User | None:
        """Fetch a user by primary key.

        Args:
            user_id: The UUID of the user.

        Returns:
            The matching User, or None if not found.
        """
        return await self.session.get(User, user_id)

    async def create(self, email: str, hashed_password: str) -> User:
        """Persist a new user record.

        Args:
            email: The user's email address.
            hashed_password: Pre-hashed password string.

        Returns:
            The newly created User with all DB-generated fields populated.
        """
        user = User(email=email, hashed_password=hashed_password)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user
