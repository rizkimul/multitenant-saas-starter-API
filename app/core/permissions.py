from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.workspace import WorkspaceRepository


@dataclass
class WorkspaceContext:
    """Resolved workspace + the current user's membership in it."""

    workspace: Workspace
    member: WorkspaceMember
    user: User


async def get_workspace_context(
    slug: str,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceContext:
    """Resolve the workspace by slug and verify the caller is a member.

    Args:
        slug: Workspace slug from the URL path.
        current_user: Authenticated user from the Bearer token.
        session: Injected database session.

    Returns:
        WorkspaceContext with workspace, membership, and user populated.

    Raises:
        NotFoundError: If the workspace does not exist.
        ForbiddenError: If the current user is not a member.
    """
    repo = WorkspaceRepository(session)
    workspace = await repo.get_with_members(slug)
    if not workspace:
        raise NotFoundError("Workspace")

    member = next(
        (m for m in workspace.members if m.user_id == current_user.id), None
    )
    if not member:
        raise ForbiddenError("You are not a member of this workspace")

    return WorkspaceContext(workspace=workspace, member=member, user=current_user)


def _require_role(*roles: WorkspaceRole):
    """Return a FastAPI dependency that enforces a minimum workspace role.

    Args:
        *roles: Acceptable roles — the caller must hold one of these.
    """
    async def guard(
        ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    ) -> WorkspaceContext:
        if ctx.member.role not in roles:
            required = " or ".join(r.value for r in roles)
            raise ForbiddenError(f"Required role: {required}")
        return ctx

    return guard


WorkspaceMemberCtx = Annotated[
    WorkspaceContext,
    Depends(_require_role(WorkspaceRole.member, WorkspaceRole.admin, WorkspaceRole.owner)),
]

WorkspaceAdminCtx = Annotated[
    WorkspaceContext,
    Depends(_require_role(WorkspaceRole.admin, WorkspaceRole.owner)),
]

WorkspaceOwnerCtx = Annotated[
    WorkspaceContext,
    Depends(_require_role(WorkspaceRole.owner)),
]
