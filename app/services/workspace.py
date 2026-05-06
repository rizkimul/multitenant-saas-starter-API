import re
import uuid

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.user import UserRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.workspace import MemberInvite, MemberRoleUpdate, WorkspaceCreate


class WorkspaceService:
    """Business logic for workspace and membership management."""

    def __init__(
        self,
        workspace_repo: WorkspaceRepository,
        user_repo: UserRepository,
    ) -> None:
        self.workspace_repo = workspace_repo
        self.user_repo = user_repo

    async def create_workspace(
        self, data: WorkspaceCreate, creator_id: uuid.UUID
    ) -> Workspace:
        """Create a workspace and make the creator its owner.

        Args:
            data: Validated workspace creation payload.
            creator_id: UUID of the user creating the workspace.

        Returns:
            The newly created Workspace.

        Raises:
            ConflictError: If the requested slug is already taken.
        """
        base_slug = data.slug or self._slugify(data.name)

        if data.slug and await self.workspace_repo.slug_exists(data.slug):
            raise ConflictError(f"Slug '{data.slug}' is already taken")

        slug = await self._ensure_unique_slug(base_slug) if not data.slug else base_slug

        workspace = await self.workspace_repo.create(name=data.name, slug=slug)
        await self.workspace_repo.add_member(
            workspace_id=workspace.id,
            user_id=creator_id,
            role=WorkspaceRole.owner,
        )
        return workspace

    async def get_user_workspaces(self, user_id: uuid.UUID) -> list[Workspace]:
        """List all workspaces the user belongs to.

        Args:
            user_id: The requesting user's UUID.

        Returns:
            List of Workspaces, newest first.
        """
        return await self.workspace_repo.get_user_workspaces(user_id)

    async def get_workspace(
        self, slug: str, requesting_user_id: uuid.UUID
    ) -> Workspace:
        """Fetch a workspace with members, verifying the requester is a member.

        Args:
            slug: The workspace slug.
            requesting_user_id: UUID of the user making the request.

        Returns:
            Workspace with members loaded.

        Raises:
            NotFoundError: If the workspace does not exist.
            ForbiddenError: If the requester is not a member.
        """
        workspace = await self.workspace_repo.get_with_members(slug)
        if not workspace:
            raise NotFoundError("Workspace")
        self._require_member(workspace, requesting_user_id)
        return workspace

    async def invite_member(
        self, slug: str, data: MemberInvite, actor_id: uuid.UUID
    ) -> WorkspaceMember:
        """Add a user to a workspace.

        Args:
            slug: The workspace slug.
            data: Invite payload with user_id and role.
            actor_id: UUID of the user performing the action.

        Returns:
            The new WorkspaceMember record.

        Raises:
            NotFoundError: If the workspace or invited user does not exist.
            ForbiddenError: If the actor lacks permission.
            ConflictError: If the user is already a member.
        """
        workspace = await self.workspace_repo.get_with_members(slug)
        if not workspace:
            raise NotFoundError("Workspace")

        actor_member = self._get_membership(workspace, actor_id)
        self._require_admin_or_owner(actor_member)

        if data.role == WorkspaceRole.owner:
            self._require_owner(actor_member)

        invited_user = await self.user_repo.find_by_id(data.user_id)
        if not invited_user:
            raise NotFoundError("User")

        existing = self._get_membership(workspace, data.user_id)
        if existing:
            raise ConflictError("User is already a member of this workspace")

        return await self.workspace_repo.add_member(
            workspace_id=workspace.id,
            user_id=data.user_id,
            role=data.role,
        )

    async def remove_member(
        self, slug: str, target_user_id: uuid.UUID, actor_id: uuid.UUID
    ) -> None:
        """Remove a user from a workspace.

        Args:
            slug: The workspace slug.
            target_user_id: UUID of the user to remove.
            actor_id: UUID of the user performing the action.

        Raises:
            NotFoundError: If the workspace or membership does not exist.
            ForbiddenError: If the actor lacks permission or removing last owner.
        """
        workspace = await self.workspace_repo.get_with_members(slug)
        if not workspace:
            raise NotFoundError("Workspace")

        actor_member = self._get_membership(workspace, actor_id)
        is_self_removal = actor_id == target_user_id

        if not is_self_removal:
            self._require_admin_or_owner(actor_member)

        target_member = self._get_membership(workspace, target_user_id)
        if not target_member:
            raise NotFoundError("Membership")

        if target_member.role == WorkspaceRole.owner:
            self._require_last_owner_check(workspace)

        await self.workspace_repo.remove_member(target_member)

    async def update_member_role(
        self,
        slug: str,
        target_user_id: uuid.UUID,
        data: MemberRoleUpdate,
        actor_id: uuid.UUID,
    ) -> WorkspaceMember:
        """Change a member's role within a workspace.

        Args:
            slug: The workspace slug.
            target_user_id: UUID of the member whose role is changing.
            data: Payload with the new role.
            actor_id: UUID of the user performing the action.

        Returns:
            The updated WorkspaceMember.

        Raises:
            NotFoundError: If the workspace or membership does not exist.
            ForbiddenError: If the actor lacks permission or demoting last owner.
        """
        workspace = await self.workspace_repo.get_with_members(slug)
        if not workspace:
            raise NotFoundError("Workspace")

        actor_member = self._get_membership(workspace, actor_id)
        self._require_owner(actor_member)

        target_member = self._get_membership(workspace, target_user_id)
        if not target_member:
            raise NotFoundError("Membership")

        demoting_owner = (
            target_member.role == WorkspaceRole.owner
            and data.role != WorkspaceRole.owner
        )
        if demoting_owner:
            self._require_last_owner_check(workspace)

        return await self.workspace_repo.update_member_role(target_member, data.role)

    # ── private helpers ──────────────────────────────────────────────────────

    def _slugify(self, name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return slug or "workspace"

    async def _ensure_unique_slug(self, base: str) -> str:
        if not await self.workspace_repo.slug_exists(base):
            return base
        counter = 2
        while await self.workspace_repo.slug_exists(f"{base}-{counter}"):
            counter += 1
        return f"{base}-{counter}"

    def _get_membership(
        self, workspace: Workspace, user_id: uuid.UUID
    ) -> WorkspaceMember | None:
        return next(
            (m for m in workspace.members if m.user_id == user_id), None
        )

    def _require_member(self, workspace: Workspace, user_id: uuid.UUID) -> None:
        if not self._get_membership(workspace, user_id):
            raise ForbiddenError("You are not a member of this workspace")

    def _require_admin_or_owner(self, member: WorkspaceMember | None) -> None:
        if not member or member.role not in (WorkspaceRole.admin, WorkspaceRole.owner):
            raise ForbiddenError("Admin or owner role required")

    def _require_owner(self, member: WorkspaceMember | None) -> None:
        if not member or member.role != WorkspaceRole.owner:
            raise ForbiddenError("Owner role required")

    def _require_last_owner_check(self, workspace: Workspace) -> None:
        owner_count = sum(
            1 for m in workspace.members if m.role == WorkspaceRole.owner
        )
        if owner_count <= 1:
            raise ForbiddenError("Cannot remove or demote the last owner")
