import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Payload for user registration."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class UserLogin(BaseModel):
    """Payload for user login."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Public user representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_active: bool
    is_verified: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """JWT token pair returned after successful login or refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Payload for the token refresh endpoint."""

    refresh_token: str
