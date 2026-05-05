import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole


class WorkspaceRepository:
    """Data access layer for workspaces and workspace membership."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, name: str, slug: str) -> Workspace:
        """Persist a new workspace.

        Args:
            name: Display name of the workspace.
            slug: Unique URL-friendly identifier.

        Returns:
            The newly created Workspace.
        """
        workspace = Workspace(name=name, slug=slug)
        self.session.add(workspace)
        await self.session.commit()
        await self.session.refresh(workspace)
        return workspace

    async def find_by_slug(self, slug: str) -> Workspace | None:
        """Fetch a workspace by its slug.

        Args:
            slug: The URL-friendly workspace identifier.

        Returns:
            The matching Workspace, or None.
        """
        result = await self.session.execute(
            select(Workspace).where(Workspace.slug == slug)
        )
        return result.scalars().first()

    async def slug_exists(self, slug: str) -> bool:
        """Check whether a slug is already taken.

        Args:
            slug: The slug to check.

        Returns:
            True if the slug is in use, False otherwise.
        """
        result = await self.session.execute(
            select(Workspace.id).where(Workspace.slug == slug)
        )
        return result.first() is not None

    async def get_user_workspaces(self, user_id: uuid.UUID) -> list[Workspace]:
        """List all workspaces the user is a member of.

        Args:
            user_id: The user's UUID.

        Returns:
            Workspaces ordered by creation date, newest first.
        """
        result = await self.session.execute(
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_with_members(self, slug: str) -> Workspace | None:
        """Fetch a workspace with its member list eagerly loaded.

        Args:
            slug: The workspace slug.

        Returns:
            The Workspace with members populated, or None.
        """
        result = await self.session.execute(
            select(Workspace)
            .options(selectinload(Workspace.members))
            .where(Workspace.slug == slug)
        )
        return result.scalars().first()

    async def find_member(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceMember | None:
        """Fetch a specific workspace membership by composite PK.

        Args:
            workspace_id: The workspace UUID.
            user_id: The user UUID.

        Returns:
            The WorkspaceMember, or None if the user is not a member.
        """
        return await self.session.get(WorkspaceMember, (workspace_id, user_id))

    async def add_member(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        role: WorkspaceRole,
    ) -> WorkspaceMember:
        """Add a user to a workspace with the given role.

        Args:
            workspace_id: The workspace UUID.
            user_id: The user UUID.
            role: The role to assign.

        Returns:
            The new WorkspaceMember record.
        """
        member = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=role
        )
        self.session.add(member)
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def remove_member(self, member: WorkspaceMember) -> None:
        """Delete a workspace membership record.

        Args:
            member: The WorkspaceMember to remove.
        """
        await self.session.delete(member)
        await self.session.commit()

    async def update_member_role(
        self, member: WorkspaceMember, role: WorkspaceRole
    ) -> WorkspaceMember:
        """Change a member's role within a workspace.

        Args:
            member: The existing WorkspaceMember to update.
            role: The new role to assign.

        Returns:
            The updated WorkspaceMember.
        """
        member.role = role
        await self.session.commit()
        await self.session.refresh(member)
        return member
