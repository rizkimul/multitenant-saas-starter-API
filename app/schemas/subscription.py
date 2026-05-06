import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl

from app.models.subscription import SubscriptionStatus


class BillingSetupResponse(BaseModel):
    """Returned after Stripe customer creation for a workspace."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    stripe_customer_id: str
    status: SubscriptionStatus
    created_at: datetime


class CheckoutRequest(BaseModel):
    """Payload for initiating a Stripe Checkout session."""

    success_url: HttpUrl
    cancel_url: HttpUrl


class CheckoutResponse(BaseModel):
    """URL to redirect the user to for Stripe-hosted checkout."""

    url: str


class SubscriptionResponse(BaseModel):
    """Current subscription state for a workspace."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    stripe_customer_id: str
    stripe_subscription_id: str | None
    stripe_price_id: str | None
    status: SubscriptionStatus
    current_period_end: datetime | None
    cancel_at_period_end: bool
    created_at: datetime
    updated_at: datetime
