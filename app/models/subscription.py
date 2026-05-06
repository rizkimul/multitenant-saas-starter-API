import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.workspace import Workspace


class SubscriptionStatus(enum.StrEnum):
    """Mirrors Stripe subscription statuses."""

    incomplete = "incomplete"
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    canceled = "canceled"
    unpaid = "unpaid"


class Subscription(Base):
    """Local mirror of a Stripe subscription, scoped to one workspace."""

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, index=True
    )
    stripe_customer_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True
    )
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    stripe_price_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscriptionstatus"),
        nullable=False,
        default=SubscriptionStatus.incomplete,
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="subscription")
