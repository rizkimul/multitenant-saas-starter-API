import uuid
from datetime import UTC, datetime
from typing import Any

import stripe

from app.core.config import get_settings
from app.core.exceptions import AppError, NotFoundError
from app.models.subscription import Subscription, SubscriptionStatus
from app.repositories.subscription import SubscriptionRepository


class SubscriptionService:
    """Orchestrates Stripe billing and local subscription state."""

    def __init__(self, sub_repo: SubscriptionRepository) -> None:
        self.sub_repo = sub_repo
        self._settings = get_settings()
        stripe.api_key = self._settings.stripe_secret_key

    async def get_or_create_customer(
        self,
        workspace_id: uuid.UUID,
        workspace_name: str,
        owner_email: str,
    ) -> Subscription:
        """Return the workspace subscription, creating a Stripe customer if needed.

        Args:
            workspace_id: The workspace UUID.
            workspace_name: Used as the Stripe customer name.
            owner_email: Owner's email, attached to the Stripe customer.

        Returns:
            The existing or newly created Subscription record.
        """
        existing = await self.sub_repo.get_by_workspace_id(workspace_id)
        if existing:
            return existing

        customer = stripe.Customer.create(
            name=workspace_name,
            email=owner_email,
            metadata={"workspace_id": str(workspace_id)},
        )
        return await self.sub_repo.create(
            workspace_id=workspace_id,
            stripe_customer_id=customer.id,
        )

    async def create_checkout_session(
        self,
        workspace_id: uuid.UUID,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Create a Stripe Checkout session and return the redirect URL.

        Args:
            workspace_id: The workspace subscribing.
            success_url: URL Stripe redirects to on success.
            cancel_url: URL Stripe redirects to on cancel.

        Returns:
            The Stripe-hosted checkout URL.

        Raises:
            NotFoundError: If no Stripe customer exists for this workspace yet.
        """
        sub = await self.sub_repo.get_by_workspace_id(workspace_id)
        if not sub:
            raise NotFoundError("Subscription")

        session = stripe.checkout.Session.create(
            customer=sub.stripe_customer_id,
            mode="subscription",
            line_items=[{"price": self._settings.stripe_price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return session.url  # type: ignore[return-value]

    async def handle_webhook(self, payload: bytes, sig_header: str) -> None:
        """Verify and dispatch an incoming Stripe webhook event.

        Args:
            payload: Raw request body bytes.
            sig_header: Value of the ``Stripe-Signature`` header.

        Raises:
            AppError: If the signature is invalid or the event payload is malformed.
        """
        try:
            event = stripe.Webhook.construct_event(  # type: ignore[no-untyped-call]
                payload, sig_header, self._settings.stripe_webhook_secret
            )
        except stripe.SignatureVerificationError:
            raise AppError("Invalid webhook signature", status_code=400)
        except ValueError:
            raise AppError("Invalid webhook payload", status_code=400)

        event_type: str = event["type"]
        data = event["data"]["object"]

        if event_type == "customer.subscription.updated":
            await self._sync_subscription(data)
        elif event_type == "customer.subscription.deleted":
            await self._cancel_subscription(data)

    async def _sync_subscription(self, data: dict[str, Any]) -> None:
        """Update local subscription from a Stripe subscription object.

        Args:
            data: The Stripe subscription object from the webhook payload.
        """
        customer_id: str = data["customer"]
        sub = await self.sub_repo.get_by_stripe_customer_id(customer_id)
        if not sub:
            return

        raw_status = data.get("status", "")
        try:
            status = SubscriptionStatus(raw_status)
        except ValueError:
            status = SubscriptionStatus.incomplete

        period_end = datetime.fromtimestamp(
            data["current_period_end"], tz=UTC
        )

        await self.sub_repo.update(
            sub,
            stripe_subscription_id=data["id"],
            stripe_price_id=data["items"]["data"][0]["price"]["id"],
            status=status,
            current_period_end=period_end,
            cancel_at_period_end=data.get("cancel_at_period_end", False),
        )

    async def _cancel_subscription(self, data: dict[str, Any]) -> None:
        """Mark a subscription as canceled when Stripe deletes it.

        Args:
            data: The Stripe subscription object from the webhook payload.
        """
        customer_id: str = data["customer"]
        sub = await self.sub_repo.get_by_stripe_customer_id(customer_id)
        if not sub:
            return

        await self.sub_repo.update(sub, status=SubscriptionStatus.canceled)
