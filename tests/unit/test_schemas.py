import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.subscription import SubscriptionStatus
from app.schemas.subscription import (
    BillingSetupResponse,
    CheckoutRequest,
    CheckoutResponse,
    SubscriptionResponse,
)


class TestCheckoutRequest:
    def test_valid_urls_accepted(self) -> None:
        req = CheckoutRequest(
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )
        assert str(req.success_url).startswith("https://example.com")

    def test_invalid_url_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest(success_url="not-a-url", cancel_url="https://example.com")


class TestCheckoutResponse:
    def test_holds_url_string(self) -> None:
        resp = CheckoutResponse(url="https://checkout.stripe.com/pay/cs_test")
        assert resp.url == "https://checkout.stripe.com/pay/cs_test"


class TestBillingSetupResponse:
    def test_from_attributes(self) -> None:
        workspace_id = uuid.uuid4()
        obj_id = uuid.uuid4()
        now = datetime.now(UTC)

        data = {
            "id": obj_id,
            "workspace_id": workspace_id,
            "stripe_customer_id": "cus_test",
            "status": SubscriptionStatus.incomplete,
            "created_at": now,
        }
        resp = BillingSetupResponse.model_validate(data)

        assert resp.stripe_customer_id == "cus_test"
        assert resp.status == SubscriptionStatus.incomplete


class TestSubscriptionResponse:
    def test_full_response_from_attributes(self) -> None:
        now = datetime.now(UTC)
        data = {
            "id": uuid.uuid4(),
            "workspace_id": uuid.uuid4(),
            "stripe_customer_id": "cus_test",
            "stripe_subscription_id": "sub_test",
            "stripe_price_id": "price_test",
            "status": SubscriptionStatus.active,
            "current_period_end": now,
            "cancel_at_period_end": False,
            "created_at": now,
            "updated_at": now,
        }
        resp = SubscriptionResponse.model_validate(data)

        assert resp.status == SubscriptionStatus.active
        assert resp.cancel_at_period_end is False

    def test_nullable_fields_accept_none(self) -> None:
        now = datetime.now(UTC)
        data = {
            "id": uuid.uuid4(),
            "workspace_id": uuid.uuid4(),
            "stripe_customer_id": "cus_test",
            "stripe_subscription_id": None,
            "stripe_price_id": None,
            "status": SubscriptionStatus.incomplete,
            "current_period_end": None,
            "cancel_at_period_end": False,
            "created_at": now,
            "updated_at": now,
        }
        resp = SubscriptionResponse.model_validate(data)

        assert resp.stripe_subscription_id is None
        assert resp.current_period_end is None
