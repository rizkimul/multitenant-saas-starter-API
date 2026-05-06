import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import stripe

from app.core.exceptions import AppError, NotFoundError
from app.models.subscription import Subscription, SubscriptionStatus
from app.services.subscription import SubscriptionService

WORKSPACE_ID = uuid.uuid4()
CUSTOMER_ID = "cus_test123"
SUBSCRIPTION_ID = "sub_test456"
PRICE_ID = "price_test789"


def make_subscription(
    *,
    status: SubscriptionStatus = SubscriptionStatus.incomplete,
    stripe_subscription_id: str | None = None,
) -> MagicMock:
    sub = MagicMock(spec=Subscription)
    sub.id = uuid.uuid4()
    sub.workspace_id = WORKSPACE_ID
    sub.stripe_customer_id = CUSTOMER_ID
    sub.stripe_subscription_id = stripe_subscription_id
    sub.stripe_price_id = PRICE_ID
    sub.status = status
    sub.current_period_end = None
    sub.cancel_at_period_end = False
    sub.created_at = datetime.now(UTC)
    sub.updated_at = datetime.now(UTC)
    return sub


def make_stripe_subscription_data(
    *,
    customer_id: str = CUSTOMER_ID,
    subscription_id: str = SUBSCRIPTION_ID,
    price_id: str = PRICE_ID,
    status: str = "active",
    period_end: int = 1_800_000_000,
    cancel_at_period_end: bool = False,
) -> dict:
    return {
        "id": subscription_id,
        "customer": customer_id,
        "status": status,
        "current_period_end": period_end,
        "cancel_at_period_end": cancel_at_period_end,
        "items": {"data": [{"price": {"id": price_id}}]},
    }


@pytest.fixture
def mock_sub_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_sub_repo: AsyncMock) -> SubscriptionService:
    with patch("app.services.subscription.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            stripe_secret_key="sk_test_dummy",
            stripe_webhook_secret="whsec_dummy",
            stripe_price_id=PRICE_ID,
        )
        return SubscriptionService(sub_repo=mock_sub_repo)


class TestGetOrCreateCustomer:
    async def test_returns_existing_subscription(
        self, service: SubscriptionService, mock_sub_repo: AsyncMock
    ) -> None:
        existing = make_subscription()
        mock_sub_repo.get_by_workspace_id.return_value = existing

        result = await service.get_or_create_customer(
            workspace_id=WORKSPACE_ID,
            workspace_name="Acme",
            owner_email="owner@acme.com",
        )

        assert result is existing
        mock_sub_repo.create.assert_not_called()

    async def test_creates_stripe_customer_when_none_exists(
        self, service: SubscriptionService, mock_sub_repo: AsyncMock
    ) -> None:
        mock_sub_repo.get_by_workspace_id.return_value = None
        new_sub = make_subscription()
        mock_sub_repo.create.return_value = new_sub

        fake_customer = MagicMock()
        fake_customer.id = CUSTOMER_ID

        with patch("stripe.Customer.create", return_value=fake_customer) as mock_create:
            result = await service.get_or_create_customer(
                workspace_id=WORKSPACE_ID,
                workspace_name="Acme",
                owner_email="owner@acme.com",
            )

        mock_create.assert_called_once_with(
            name="Acme",
            email="owner@acme.com",
            metadata={"workspace_id": str(WORKSPACE_ID)},
        )
        mock_sub_repo.create.assert_called_once_with(
            workspace_id=WORKSPACE_ID,
            stripe_customer_id=CUSTOMER_ID,
        )
        assert result is new_sub


class TestCreateCheckoutSession:
    async def test_raises_not_found_when_no_subscription(
        self, service: SubscriptionService, mock_sub_repo: AsyncMock
    ) -> None:
        mock_sub_repo.get_by_workspace_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.create_checkout_session(
                workspace_id=WORKSPACE_ID,
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )

    async def test_returns_checkout_url(
        self, service: SubscriptionService, mock_sub_repo: AsyncMock
    ) -> None:
        mock_sub_repo.get_by_workspace_id.return_value = make_subscription()

        fake_session = MagicMock()
        fake_session.url = "https://checkout.stripe.com/pay/cs_test_abc"

        with patch("stripe.checkout.Session.create", return_value=fake_session):
            url = await service.create_checkout_session(
                workspace_id=WORKSPACE_ID,
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )

        assert url == "https://checkout.stripe.com/pay/cs_test_abc"

    async def test_passes_correct_params_to_stripe(
        self, service: SubscriptionService, mock_sub_repo: AsyncMock
    ) -> None:
        mock_sub_repo.get_by_workspace_id.return_value = make_subscription()
        fake_session = MagicMock()
        fake_session.url = "https://checkout.stripe.com/pay/cs_test"

        with patch(
            "stripe.checkout.Session.create", return_value=fake_session
        ) as mock_create:
            await service.create_checkout_session(
                workspace_id=WORKSPACE_ID,
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )

        mock_create.assert_called_once_with(
            customer=CUSTOMER_ID,
            mode="subscription",
            line_items=[{"price": PRICE_ID, "quantity": 1}],
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )


class TestHandleWebhook:
    async def test_raises_on_invalid_signature(
        self, service: SubscriptionService
    ) -> None:
        with patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe.SignatureVerificationError("bad sig", "header"),
        ):
            with pytest.raises(AppError, match="Invalid webhook signature"):
                await service.handle_webhook(b"payload", "bad-sig")

    async def test_raises_on_invalid_payload(
        self, service: SubscriptionService
    ) -> None:
        with patch(
            "stripe.Webhook.construct_event",
            side_effect=ValueError("bad json"),
        ):
            with pytest.raises(AppError, match="Invalid webhook payload"):
                await service.handle_webhook(b"not-json", "sig")

    async def test_dispatches_subscription_updated(
        self, service: SubscriptionService, mock_sub_repo: AsyncMock
    ) -> None:
        data = make_stripe_subscription_data()
        event = {"type": "customer.subscription.updated", "data": {"object": data}}
        existing = make_subscription()
        mock_sub_repo.get_by_stripe_customer_id.return_value = existing
        mock_sub_repo.update.return_value = existing

        with patch("stripe.Webhook.construct_event", return_value=event):
            await service.handle_webhook(b"payload", "sig")

        mock_sub_repo.update.assert_called_once()

    async def test_dispatches_subscription_deleted(
        self, service: SubscriptionService, mock_sub_repo: AsyncMock
    ) -> None:
        data = make_stripe_subscription_data(status="canceled")
        event = {"type": "customer.subscription.deleted", "data": {"object": data}}
        existing = make_subscription(status=SubscriptionStatus.active)
        mock_sub_repo.get_by_stripe_customer_id.return_value = existing
        mock_sub_repo.update.return_value = existing

        with patch("stripe.Webhook.construct_event", return_value=event):
            await service.handle_webhook(b"payload", "sig")

        mock_sub_repo.update.assert_called_once_with(
            existing, status=SubscriptionStatus.canceled
        )

    async def test_ignores_unknown_event_types(
        self, service: SubscriptionService, mock_sub_repo: AsyncMock
    ) -> None:
        event = {"type": "payment_intent.created", "data": {"object": {}}}

        with patch("stripe.Webhook.construct_event", return_value=event):
            await service.handle_webhook(b"payload", "sig")

        mock_sub_repo.update.assert_not_called()


class TestSyncSubscription:
    async def test_updates_all_fields_from_stripe_data(
        self, service: SubscriptionService, mock_sub_repo: AsyncMock
    ) -> None:
        data = make_stripe_subscription_data(
            status="active",
            period_end=1_800_000_000,
            cancel_at_period_end=True,
        )
        event = {"type": "customer.subscription.updated", "data": {"object": data}}
        existing = make_subscription()
        mock_sub_repo.get_by_stripe_customer_id.return_value = existing
        mock_sub_repo.update.return_value = existing

        with patch("stripe.Webhook.construct_event", return_value=event):
            await service.handle_webhook(b"payload", "sig")

        call_kwargs = mock_sub_repo.update.call_args
        assert call_kwargs.kwargs["status"] == SubscriptionStatus.active
        assert call_kwargs.kwargs["stripe_subscription_id"] == SUBSCRIPTION_ID
        assert call_kwargs.kwargs["stripe_price_id"] == PRICE_ID
        assert call_kwargs.kwargs["cancel_at_period_end"] is True
        assert call_kwargs.kwargs["current_period_end"] == datetime.fromtimestamp(
            1_800_000_000, tz=UTC
        )

    async def test_unknown_stripe_status_falls_back_to_incomplete(
        self, service: SubscriptionService, mock_sub_repo: AsyncMock
    ) -> None:
        data = make_stripe_subscription_data(status="paused")
        event = {"type": "customer.subscription.updated", "data": {"object": data}}
        existing = make_subscription()
        mock_sub_repo.get_by_stripe_customer_id.return_value = existing
        mock_sub_repo.update.return_value = existing

        with patch("stripe.Webhook.construct_event", return_value=event):
            await service.handle_webhook(b"payload", "sig")

        call_kwargs = mock_sub_repo.update.call_args
        assert call_kwargs.kwargs["status"] == SubscriptionStatus.incomplete

    async def test_silently_skips_unknown_customer(
        self, service: SubscriptionService, mock_sub_repo: AsyncMock
    ) -> None:
        data = make_stripe_subscription_data(customer_id="cus_unknown")
        event = {"type": "customer.subscription.updated", "data": {"object": data}}
        mock_sub_repo.get_by_stripe_customer_id.return_value = None

        with patch("stripe.Webhook.construct_event", return_value=event):
            await service.handle_webhook(b"payload", "sig")

        mock_sub_repo.update.assert_not_called()
