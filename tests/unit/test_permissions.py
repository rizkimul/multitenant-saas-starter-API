import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import WorkspaceContext, _require_role, get_workspace_context
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole


def make_member(
    workspace_id: uuid.UUID, user_id: uuid.UUID, role: WorkspaceRole
) -> MagicMock:
    m = MagicMock(spec=WorkspaceMember)
    m.workspace_id = workspace_id
    m.user_id = user_id
    m.role = role
    m.created_at = datetime.now(UTC)
    return m


def make_workspace(members: dict[uuid.UUID, WorkspaceRole]) -> MagicMock:
    workspace = MagicMock(spec=Workspace)
    workspace.id = uuid.uuid4()
    workspace.slug = "test-workspace"
    workspace.members = [
        make_member(workspace.id, uid, role) for uid, role in members.items()
    ]
    return workspace


OWNER_ID = uuid.uuid4()
MEMBER_ID = uuid.uuid4()
OUTSIDER_ID = uuid.uuid4()


class TestGetWorkspaceContext:
    async def test_returns_context_for_member(self) -> None:
        workspace = make_workspace(
            {OWNER_ID: WorkspaceRole.owner, MEMBER_ID: WorkspaceRole.member}
        )
        mock_user = MagicMock(id=MEMBER_ID)
        mock_repo = AsyncMock()
        mock_repo.get_with_members.return_value = workspace

        with patch("app.core.permissions.WorkspaceRepository", return_value=mock_repo):
            ctx = await get_workspace_context(
                slug="test-workspace",
                current_user=mock_user,
                session=AsyncMock(),
            )

        assert ctx.workspace is workspace
        assert ctx.member.user_id == MEMBER_ID
        assert ctx.user is mock_user

    async def test_raises_not_found_for_missing_workspace(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.get_with_members.return_value = None

        with patch("app.core.permissions.WorkspaceRepository", return_value=mock_repo):
            with pytest.raises(NotFoundError):
                await get_workspace_context(
                    slug="ghost",
                    current_user=MagicMock(id=OUTSIDER_ID),
                    session=AsyncMock(),
                )

    async def test_raises_forbidden_for_non_member(self) -> None:
        workspace = make_workspace({OWNER_ID: WorkspaceRole.owner})
        mock_repo = AsyncMock()
        mock_repo.get_with_members.return_value = workspace

        with patch("app.core.permissions.WorkspaceRepository", return_value=mock_repo):
            with pytest.raises(ForbiddenError):
                await get_workspace_context(
                    slug="test-workspace",
                    current_user=MagicMock(id=OUTSIDER_ID),
                    session=AsyncMock(),
                )


class TestRequireRole:
    def _make_ctx(self, role: WorkspaceRole) -> WorkspaceContext:
        workspace = make_workspace({OWNER_ID: role})
        member = workspace.members[0]
        return WorkspaceContext(workspace=workspace, member=member, user=MagicMock())

    async def test_passes_when_role_matches(self) -> None:
        guard = _require_role(WorkspaceRole.admin, WorkspaceRole.owner)
        ctx = self._make_ctx(WorkspaceRole.owner)
        result = await guard(ctx)
        assert result is ctx

    async def test_raises_forbidden_when_role_insufficient(self) -> None:
        guard = _require_role(WorkspaceRole.admin, WorkspaceRole.owner)
        ctx = self._make_ctx(WorkspaceRole.member)
        with pytest.raises(ForbiddenError, match="Required role"):
            await guard(ctx)

    async def test_member_passes_member_guard(self) -> None:
        guard = _require_role(
            WorkspaceRole.member, WorkspaceRole.admin, WorkspaceRole.owner
        )
        ctx = self._make_ctx(WorkspaceRole.member)
        result = await guard(ctx)
        assert result is ctx

    async def test_owner_passes_admin_guard(self) -> None:
        guard = _require_role(WorkspaceRole.admin, WorkspaceRole.owner)
        ctx = self._make_ctx(WorkspaceRole.owner)
        result = await guard(ctx)
        assert result is ctx
