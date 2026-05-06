import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.schemas.workspace import MemberInvite, MemberRoleUpdate, WorkspaceCreate
from app.services.workspace import WorkspaceService

# Fixed IDs for readable assertions
OWNER_ID = uuid.uuid4()
ADMIN_ID = uuid.uuid4()
MEMBER_ID = uuid.uuid4()
OUTSIDER_ID = uuid.uuid4()


def make_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    role: WorkspaceRole,
) -> MagicMock:
    m = MagicMock(spec=WorkspaceMember)
    m.workspace_id = workspace_id
    m.user_id = user_id
    m.role = role
    m.created_at = datetime.now(UTC)
    return m


def make_workspace(
    roles: dict[uuid.UUID, WorkspaceRole],
    slug: str = "test-workspace",
) -> MagicMock:
    """Build a mock Workspace whose .members list reflects the given roles."""
    workspace = MagicMock(spec=Workspace)
    workspace.id = uuid.uuid4()
    workspace.name = "Test Workspace"
    workspace.slug = slug
    workspace.created_at = datetime.now(UTC)
    workspace.members = [
        make_member(workspace.id, user_id, role)
        for user_id, role in roles.items()
    ]
    return workspace


@pytest.fixture
def mock_workspace_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_user_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    mock_workspace_repo: AsyncMock, mock_user_repo: AsyncMock
) -> WorkspaceService:
    return WorkspaceService(
        workspace_repo=mock_workspace_repo,
        user_repo=mock_user_repo,
    )


class TestCreateWorkspace:
    async def test_success_with_provided_slug(
        self, service: WorkspaceService, mock_workspace_repo: AsyncMock
    ) -> None:
        mock_workspace_repo.slug_exists.return_value = False
        mock_workspace_repo.create.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner}
        )
        mock_workspace_repo.add_member.return_value = MagicMock()

        await service.create_workspace(
            WorkspaceCreate(name="Test Workspace", slug="my-slug"), OWNER_ID
        )

        mock_workspace_repo.create.assert_called_once_with(
            name="Test Workspace", slug="my-slug"
        )

    async def test_auto_generates_slug_from_name(
        self, service: WorkspaceService, mock_workspace_repo: AsyncMock
    ) -> None:
        mock_workspace_repo.slug_exists.return_value = False
        mock_workspace_repo.create.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner}
        )
        mock_workspace_repo.add_member.return_value = MagicMock()

        await service.create_workspace(
            WorkspaceCreate(name="My Cool Team"), OWNER_ID
        )

        mock_workspace_repo.create.assert_called_once_with(
            name="My Cool Team", slug="my-cool-team"
        )

    async def test_appends_counter_when_slug_taken(
        self, service: WorkspaceService, mock_workspace_repo: AsyncMock
    ) -> None:
        # base slug taken, "-2" also taken, "-3" is free
        mock_workspace_repo.slug_exists.side_effect = [True, True, False]
        mock_workspace_repo.create.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner}
        )
        mock_workspace_repo.add_member.return_value = MagicMock()

        await service.create_workspace(WorkspaceCreate(name="My Team"), OWNER_ID)

        mock_workspace_repo.create.assert_called_once_with(
            name="My Team", slug="my-team-3"
        )

    async def test_conflict_on_taken_custom_slug(
        self, service: WorkspaceService, mock_workspace_repo: AsyncMock
    ) -> None:
        mock_workspace_repo.slug_exists.return_value = True

        with pytest.raises(ConflictError, match="already taken"):
            await service.create_workspace(
                WorkspaceCreate(name="Test", slug="taken-slug"), OWNER_ID
            )

    async def test_creator_added_as_owner(
        self, service: WorkspaceService, mock_workspace_repo: AsyncMock
    ) -> None:
        workspace = make_workspace({OWNER_ID: WorkspaceRole.owner})
        mock_workspace_repo.slug_exists.return_value = False
        mock_workspace_repo.create.return_value = workspace
        mock_workspace_repo.add_member.return_value = MagicMock()

        await service.create_workspace(WorkspaceCreate(name="Test"), OWNER_ID)

        mock_workspace_repo.add_member.assert_called_once_with(
            workspace_id=workspace.id,
            user_id=OWNER_ID,
            role=WorkspaceRole.owner,
        )


class TestGetWorkspace:
    async def test_success_for_member(
        self, service: WorkspaceService, mock_workspace_repo: AsyncMock
    ) -> None:
        workspace = make_workspace(
            {OWNER_ID: WorkspaceRole.owner, MEMBER_ID: WorkspaceRole.member}
        )
        mock_workspace_repo.get_with_members.return_value = workspace

        result = await service.get_workspace("test-workspace", MEMBER_ID)

        assert result is workspace

    async def test_not_found(
        self, service: WorkspaceService, mock_workspace_repo: AsyncMock
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = None

        with pytest.raises(NotFoundError):
            await service.get_workspace("missing", OWNER_ID)

    async def test_outsider_cannot_view(
        self, service: WorkspaceService, mock_workspace_repo: AsyncMock
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner}
        )

        with pytest.raises(ForbiddenError):
            await service.get_workspace("test-workspace", OUTSIDER_ID)


class TestInviteMember:
    async def test_owner_can_invite(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
        mock_user_repo: AsyncMock,
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner}
        )
        mock_user_repo.find_by_id.return_value = MagicMock()
        mock_workspace_repo.add_member.return_value = MagicMock()

        await service.invite_member(
            "test-workspace",
            MemberInvite(user_id=OUTSIDER_ID, role=WorkspaceRole.member),
            actor_id=OWNER_ID,
        )

        mock_workspace_repo.add_member.assert_called_once()

    async def test_admin_can_invite(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
        mock_user_repo: AsyncMock,
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner, ADMIN_ID: WorkspaceRole.admin}
        )
        mock_user_repo.find_by_id.return_value = MagicMock()
        mock_workspace_repo.add_member.return_value = MagicMock()

        await service.invite_member(
            "test-workspace",
            MemberInvite(user_id=OUTSIDER_ID),
            actor_id=ADMIN_ID,
        )

        mock_workspace_repo.add_member.assert_called_once()

    async def test_member_cannot_invite(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner, MEMBER_ID: WorkspaceRole.member}
        )

        with pytest.raises(ForbiddenError, match="Admin or owner role required"):
            await service.invite_member(
                "test-workspace",
                MemberInvite(user_id=OUTSIDER_ID),
                actor_id=MEMBER_ID,
            )

    async def test_admin_cannot_assign_owner_role(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner, ADMIN_ID: WorkspaceRole.admin}
        )

        with pytest.raises(ForbiddenError, match="Owner role required"):
            await service.invite_member(
                "test-workspace",
                MemberInvite(user_id=OUTSIDER_ID, role=WorkspaceRole.owner),
                actor_id=ADMIN_ID,
            )

    async def test_already_member_raises_conflict(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
        mock_user_repo: AsyncMock,
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner, MEMBER_ID: WorkspaceRole.member}
        )
        mock_user_repo.find_by_id.return_value = MagicMock()

        with pytest.raises(ConflictError, match="already a member"):
            await service.invite_member(
                "test-workspace",
                MemberInvite(user_id=MEMBER_ID),
                actor_id=OWNER_ID,
            )

    async def test_invited_user_not_found(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
        mock_user_repo: AsyncMock,
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner}
        )
        mock_user_repo.find_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.invite_member(
                "test-workspace",
                MemberInvite(user_id=OUTSIDER_ID),
                actor_id=OWNER_ID,
            )


class TestRemoveMember:
    async def test_owner_can_remove_member(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner, MEMBER_ID: WorkspaceRole.member}
        )

        await service.remove_member("test-workspace", MEMBER_ID, actor_id=OWNER_ID)

        mock_workspace_repo.remove_member.assert_called_once()

    async def test_member_can_remove_themselves(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner, MEMBER_ID: WorkspaceRole.member}
        )

        await service.remove_member("test-workspace", MEMBER_ID, actor_id=MEMBER_ID)

        mock_workspace_repo.remove_member.assert_called_once()

    async def test_member_cannot_remove_others(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
    ) -> None:
        other_id = uuid.uuid4()
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {
                OWNER_ID: WorkspaceRole.owner,
                MEMBER_ID: WorkspaceRole.member,
                other_id: WorkspaceRole.member,
            }
        )

        with pytest.raises(ForbiddenError):
            await service.remove_member("test-workspace", other_id, actor_id=MEMBER_ID)

    async def test_cannot_remove_last_owner(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner, MEMBER_ID: WorkspaceRole.member}
        )

        with pytest.raises(ForbiddenError, match="last owner"):
            await service.remove_member("test-workspace", OWNER_ID, actor_id=OWNER_ID)


class TestUpdateMemberRole:
    async def test_owner_can_change_role(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner, MEMBER_ID: WorkspaceRole.member}
        )
        mock_workspace_repo.update_member_role.return_value = MagicMock()

        await service.update_member_role(
            "test-workspace",
            MEMBER_ID,
            MemberRoleUpdate(role=WorkspaceRole.admin),
            OWNER_ID,
        )

        mock_workspace_repo.update_member_role.assert_called_once()

    async def test_admin_cannot_change_roles(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {
                OWNER_ID: WorkspaceRole.owner,
                ADMIN_ID: WorkspaceRole.admin,
                MEMBER_ID: WorkspaceRole.member,
            }
        )

        with pytest.raises(ForbiddenError, match="Owner role required"):
            await service.update_member_role(
                "test-workspace",
                MEMBER_ID,
                MemberRoleUpdate(role=WorkspaceRole.admin),
                ADMIN_ID,
            )

    async def test_cannot_demote_last_owner(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
    ) -> None:
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner, MEMBER_ID: WorkspaceRole.member}
        )

        with pytest.raises(ForbiddenError, match="last owner"):
            await service.update_member_role(
                "test-workspace",
                OWNER_ID,
                MemberRoleUpdate(role=WorkspaceRole.admin),
                OWNER_ID,
            )

    async def test_second_owner_can_be_demoted(
        self,
        service: WorkspaceService,
        mock_workspace_repo: AsyncMock,
    ) -> None:
        second_owner_id = uuid.uuid4()
        mock_workspace_repo.get_with_members.return_value = make_workspace(
            {OWNER_ID: WorkspaceRole.owner, second_owner_id: WorkspaceRole.owner}
        )
        mock_workspace_repo.update_member_role.return_value = MagicMock()

        await service.update_member_role(
            "test-workspace",
            second_owner_id,
            MemberRoleUpdate(role=WorkspaceRole.admin),
            OWNER_ID,
        )

        mock_workspace_repo.update_member_role.assert_called_once()


class TestSlugify:
    def test_lowercases_and_hyphenates(self, service: WorkspaceService) -> None:
        assert service._slugify("My Cool Team") == "my-cool-team"

    def test_strips_special_characters(self, service: WorkspaceService) -> None:
        assert service._slugify("Acme Corp!") == "acme-corp"

    def test_collapses_multiple_separators(self, service: WorkspaceService) -> None:
        assert service._slugify("hello   world") == "hello-world"

    def test_fallback_for_empty_result(self, service: WorkspaceService) -> None:
        assert service._slugify("!!!") == "workspace"
