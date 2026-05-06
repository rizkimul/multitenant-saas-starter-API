import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.subscription import SubscriptionStatus
from app.models.workspace import WorkspaceRole
from app.workers.tasks.email import send_subscription_confirmed_email, send_welcome_email
from app.workers.tasks.report import _build_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_workspace_mock(workspace_id: uuid.UUID, name: str = "Acme") -> MagicMock:
    ws = MagicMock()
    ws.id = workspace_id
    ws.name = name
    return ws


def make_subscription_mock(
    *,
    status: SubscriptionStatus = SubscriptionStatus.active,
    period_end: datetime | None = None,
    cancel_at_period_end: bool = False,
) -> MagicMock:
    sub = MagicMock()
    sub.status = status
    sub.stripe_customer_id = "cus_test"
    sub.current_period_end = period_end
    sub.cancel_at_period_end = cancel_at_period_end
    return sub


# ---------------------------------------------------------------------------
# Email tasks
# ---------------------------------------------------------------------------

class TestSendWelcomeEmail:
    def test_calls_send_with_correct_args(self) -> None:
        user_id = str(uuid.uuid4())

        with patch("app.workers.tasks.email._send") as mock_send:
            result = send_welcome_email.run(user_id=user_id, email="user@example.com", name="Alice")

        mock_send.assert_called_once_with(
            to="user@example.com",
            subject="Welcome to SaaS Starter!",
            body="Hi Alice,\n\nThanks for signing up. Your account is ready.\n",
        )
        assert result["status"] == "sent"
        assert result["user_id"] == user_id

    def test_retries_on_exception(self) -> None:
        with patch("app.workers.tasks.email._send", side_effect=RuntimeError("smtp down")):
            with patch.object(send_welcome_email, "retry", side_effect=Exception("retry called")):
                with pytest.raises(Exception, match="retry called"):
                    send_welcome_email.run(
                        user_id=str(uuid.uuid4()),
                        email="user@example.com",
                        name="Alice",
                    )


class TestSendSubscriptionConfirmedEmail:
    def test_calls_send_with_correct_args(self) -> None:
        workspace_id = str(uuid.uuid4())

        with patch("app.workers.tasks.email._send") as mock_send:
            result = send_subscription_confirmed_email.run(
                workspace_id=workspace_id,
                workspace_name="Acme Corp",
                email="owner@acme.com",
            )

        mock_send.assert_called_once_with(
            to="owner@acme.com",
            subject="Subscription active — Acme Corp",
            body=(
                "Hi,\n\nYour subscription for Acme Corp is now active. "
                "Enjoy all features!\n"
            ),
        )
        assert result["status"] == "sent"
        assert result["workspace_id"] == workspace_id

    def test_retries_on_exception(self) -> None:
        with patch("app.workers.tasks.email._send", side_effect=RuntimeError("timeout")):
            with patch.object(send_subscription_confirmed_email, "retry", side_effect=Exception("retry called")):
                with pytest.raises(Exception, match="retry called"):
                    send_subscription_confirmed_email.run(
                        workspace_id=str(uuid.uuid4()),
                        workspace_name="Acme",
                        email="owner@acme.com",
                    )


# ---------------------------------------------------------------------------
# Report task — testing _build_report directly (async helper)
# ---------------------------------------------------------------------------

def _make_session_mock(
    workspace: MagicMock | None,
    role_rows: list[tuple],
    subscription: MagicMock | None,
) -> AsyncMock:
    session = AsyncMock()
    session.get.return_value = workspace

    role_result = MagicMock()
    role_result.all.return_value = role_rows

    sub_result = MagicMock()
    sub_result.scalars.return_value.first.return_value = subscription

    session.execute.side_effect = [role_result, sub_result]
    return session


class TestBuildReport:
    async def test_returns_correct_member_counts(self) -> None:
        workspace_id = uuid.uuid4()
        workspace = make_workspace_mock(workspace_id)
        role_rows = [
            (WorkspaceRole.owner, 1),
            (WorkspaceRole.admin, 2),
            (WorkspaceRole.member, 5),
        ]

        session = _make_session_mock(workspace, role_rows, subscription=None)

        with patch("app.workers.tasks.report.AsyncSessionLocal") as mock_cm:
            mock_cm.return_value.__aenter__.return_value = session
            mock_cm.return_value.__aexit__.return_value = None

            report = await _build_report(workspace_id)

        assert report["members"]["total"] == 8
        assert report["members"]["by_role"]["owner"] == 1
        assert report["members"]["by_role"]["admin"] == 2
        assert report["members"]["by_role"]["member"] == 5

    async def test_includes_subscription_fields(self) -> None:
        workspace_id = uuid.uuid4()
        workspace = make_workspace_mock(workspace_id)
        period_end = datetime(2026, 12, 31, tzinfo=timezone.utc)
        sub = make_subscription_mock(
            status=SubscriptionStatus.active,
            period_end=period_end,
            cancel_at_period_end=True,
        )

        session = _make_session_mock(workspace, [], sub)

        with patch("app.workers.tasks.report.AsyncSessionLocal") as mock_cm:
            mock_cm.return_value.__aenter__.return_value = session
            mock_cm.return_value.__aexit__.return_value = None

            report = await _build_report(workspace_id)

        assert report["subscription"]["status"] == "active"
        assert report["subscription"]["current_period_end"] == period_end.isoformat()
        assert report["subscription"]["cancel_at_period_end"] is True

    async def test_subscription_defaults_when_none(self) -> None:
        workspace_id = uuid.uuid4()
        workspace = make_workspace_mock(workspace_id)

        session = _make_session_mock(workspace, [], subscription=None)

        with patch("app.workers.tasks.report.AsyncSessionLocal") as mock_cm:
            mock_cm.return_value.__aenter__.return_value = session
            mock_cm.return_value.__aexit__.return_value = None

            report = await _build_report(workspace_id)

        assert report["subscription"]["status"] == "incomplete"
        assert report["subscription"]["stripe_customer_id"] is None
        assert report["subscription"]["current_period_end"] is None
        assert report["subscription"]["cancel_at_period_end"] is False

    async def test_raises_when_workspace_not_found(self) -> None:
        workspace_id = uuid.uuid4()
        session = AsyncMock()
        session.get.return_value = None

        with patch("app.workers.tasks.report.AsyncSessionLocal") as mock_cm:
            mock_cm.return_value.__aenter__.return_value = session
            mock_cm.return_value.__aexit__.return_value = None

            with pytest.raises(ValueError, match=str(workspace_id)):
                await _build_report(workspace_id)
