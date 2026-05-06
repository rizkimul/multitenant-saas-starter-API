import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.subscription import SubscriptionRepository
from app.repositories.user import UserRepository
from app.repositories.workspace import WorkspaceRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_execute_result(rows=None, scalar=None) -> MagicMock:
    """Build a mock SQLAlchemy execute result."""
    result = MagicMock()
    result.scalars.return_value.first.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.first.return_value = scalar
    return result


def make_session(*, execute_result=None, get_result=None) -> AsyncMock:
    session = AsyncMock()
    session.execute.return_value = execute_result or make_execute_result()
    session.get.return_value = get_result
    # session.add is sync in SQLAlchemy — override AsyncMock default
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# UserRepository
# ---------------------------------------------------------------------------

class TestUserRepository:
    async def test_find_by_email_returns_user(self) -> None:
        mock_user = MagicMock(spec=User)
        session = make_session(execute_result=make_execute_result(scalar=mock_user))
        repo = UserRepository(session)

        result = await repo.find_by_email("user@example.com")

        assert result is mock_user
        session.execute.assert_called_once()

    async def test_find_by_email_returns_none_when_missing(self) -> None:
        session = make_session(execute_result=make_execute_result(scalar=None))
        repo = UserRepository(session)

        result = await repo.find_by_email("missing@example.com")

        assert result is None

    async def test_find_by_id_delegates_to_session_get(self) -> None:
        user_id = uuid.uuid4()
        mock_user = MagicMock(spec=User)
        session = make_session(get_result=mock_user)
        repo = UserRepository(session)

        result = await repo.find_by_id(user_id)

        assert result is mock_user
        session.get.assert_called_once_with(User, user_id)

    async def test_create_adds_commits_and_refreshes(self) -> None:
        session = make_session()
        session.refresh.side_effect = lambda obj: None
        repo = UserRepository(session)

        # refresh sets state on the object — simulate by returning mock after refresh
        async def fake_refresh(obj):
            pass
        session.refresh.side_effect = fake_refresh

        session.add.return_value = None
        # Return the user after refresh via a side effect on commit
        created_user = MagicMock(spec=User)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.repositories.user.User", lambda **kw: created_user)
            result = await repo.create("user@example.com", "hashed_pw")

        session.add.assert_called_once_with(created_user)
        session.commit.assert_called_once()
        session.refresh.assert_called_once_with(created_user)
        assert result is created_user


# ---------------------------------------------------------------------------
# SubscriptionRepository
# ---------------------------------------------------------------------------

class TestSubscriptionRepository:
    async def test_get_by_workspace_id_returns_sub(self) -> None:
        mock_sub = MagicMock(spec=Subscription)
        session = make_session(execute_result=make_execute_result(scalar=mock_sub))
        repo = SubscriptionRepository(session)

        result = await repo.get_by_workspace_id(uuid.uuid4())

        assert result is mock_sub

    async def test_get_by_workspace_id_returns_none(self) -> None:
        session = make_session(execute_result=make_execute_result(scalar=None))
        repo = SubscriptionRepository(session)

        result = await repo.get_by_workspace_id(uuid.uuid4())

        assert result is None

    async def test_get_by_stripe_customer_id_returns_sub(self) -> None:
        mock_sub = MagicMock(spec=Subscription)
        session = make_session(execute_result=make_execute_result(scalar=mock_sub))
        repo = SubscriptionRepository(session)

        result = await repo.get_by_stripe_customer_id("cus_test")

        assert result is mock_sub

    async def test_create_persists_and_returns_subscription(self) -> None:
        session = make_session()
        workspace_id = uuid.uuid4()
        created_sub = MagicMock(spec=Subscription)

        async def fake_refresh(obj):
            pass
        session.refresh.side_effect = fake_refresh

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "app.repositories.subscription.Subscription",
                lambda **kw: created_sub,
            )
            result = await SubscriptionRepository(session).create(
                workspace_id=workspace_id,
                stripe_customer_id="cus_test",
            )

        session.add.assert_called_once_with(created_sub)
        session.commit.assert_called_once()
        assert result is created_sub

    async def test_update_sets_provided_fields(self) -> None:
        session = make_session()
        sub = MagicMock(spec=Subscription)
        period_end = datetime(2026, 12, 31, tzinfo=UTC)
        repo = SubscriptionRepository(session)

        await repo.update(
            sub,
            stripe_subscription_id="sub_123",
            status=SubscriptionStatus.active,
            current_period_end=period_end,
            cancel_at_period_end=True,
        )

        assert sub.stripe_subscription_id == "sub_123"
        assert sub.status == SubscriptionStatus.active
        assert sub.current_period_end == period_end
        assert sub.cancel_at_period_end is True
        session.commit.assert_called_once()
        session.refresh.assert_called_once_with(sub)

    async def test_update_skips_none_fields(self) -> None:
        session = make_session()
        sub = MagicMock(spec=Subscription)
        original_status = sub.status
        repo = SubscriptionRepository(session)

        await repo.update(sub, stripe_subscription_id="sub_new")

        assert sub.status == original_status
        assert sub.stripe_subscription_id == "sub_new"


# ---------------------------------------------------------------------------
# WorkspaceRepository (key methods)
# ---------------------------------------------------------------------------

class TestWorkspaceRepository:
    async def test_find_by_slug_returns_workspace(self) -> None:
        mock_ws = MagicMock(spec=Workspace)
        session = make_session(execute_result=make_execute_result(scalar=mock_ws))
        repo = WorkspaceRepository(session)

        result = await repo.find_by_slug("acme")

        assert result is mock_ws

    async def test_find_by_slug_returns_none(self) -> None:
        session = make_session(execute_result=make_execute_result(scalar=None))
        repo = WorkspaceRepository(session)

        result = await repo.find_by_slug("missing")

        assert result is None

    async def test_slug_exists_true(self) -> None:
        result_mock = MagicMock()
        result_mock.first.return_value = (uuid.uuid4(),)
        session = make_session(execute_result=result_mock)
        repo = WorkspaceRepository(session)

        exists = await repo.slug_exists("taken-slug")

        assert exists is True

    async def test_slug_exists_false(self) -> None:
        result_mock = MagicMock()
        result_mock.first.return_value = None
        session = make_session(execute_result=result_mock)
        repo = WorkspaceRepository(session)

        exists = await repo.slug_exists("free-slug")

        assert exists is False

    async def test_find_member_delegates_to_session_get(self) -> None:
        workspace_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mock_member = MagicMock(spec=WorkspaceMember)
        session = make_session(get_result=mock_member)
        repo = WorkspaceRepository(session)

        result = await repo.find_member(workspace_id, user_id)

        assert result is mock_member
        session.get.assert_called_once_with(WorkspaceMember, (workspace_id, user_id))

    async def test_remove_member_deletes_and_commits(self) -> None:
        session = make_session()
        member = MagicMock(spec=WorkspaceMember)
        repo = WorkspaceRepository(session)

        await repo.remove_member(member)

        session.delete.assert_called_once_with(member)
        session.commit.assert_called_once()

    async def test_update_member_role_sets_role_and_commits(self) -> None:
        session = make_session()
        member = MagicMock(spec=WorkspaceMember)
        repo = WorkspaceRepository(session)

        await repo.update_member_role(member, WorkspaceRole.admin)

        assert member.role == WorkspaceRole.admin
        session.commit.assert_called_once()
        session.refresh.assert_called_once_with(member)
