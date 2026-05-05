import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.core.permissions import WorkspaceAdminCtx, WorkspaceMemberCtx, WorkspaceOwnerCtx
from app.repositories.user import UserRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.workspace import (
    MemberInvite,
    MemberRoleUpdate,
    WorkspaceCreate,
    WorkspaceDetailResponse,
    WorkspaceMemberResponse,
    WorkspaceResponse,
)
from app.services.workspace import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


def _get_workspace_service(session: SessionDep) -> WorkspaceService:
    return WorkspaceService(
        workspace_repo=WorkspaceRepository(session),
        user_repo=UserRepository(session),
    )


WorkspaceServiceDep = Annotated[WorkspaceService, Depends(_get_workspace_service)]


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace(
    data: WorkspaceCreate,
    service: WorkspaceServiceDep,
    current_user: CurrentUser,
) -> WorkspaceResponse:
    """Create a new workspace. The creator becomes its owner."""
    workspace = await service.create_workspace(data, creator_id=current_user.id)
    return WorkspaceResponse.model_validate(workspace)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    service: WorkspaceServiceDep,
    current_user: CurrentUser,
) -> list[WorkspaceResponse]:
    """List all workspaces the current user belongs to."""
    workspaces = await service.get_user_workspaces(current_user.id)
    return [WorkspaceResponse.model_validate(w) for w in workspaces]


@router.get("/{slug}", response_model=WorkspaceDetailResponse)
async def get_workspace(ctx: WorkspaceMemberCtx) -> WorkspaceDetailResponse:
    """Get workspace details including the full member list.

    Requires: member, admin, or owner role.
    """
    return WorkspaceDetailResponse.model_validate(ctx.workspace)


@router.post(
    "/{slug}/members",
    response_model=WorkspaceMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    data: MemberInvite,
    ctx: WorkspaceAdminCtx,
    service: WorkspaceServiceDep,
) -> WorkspaceMemberResponse:
    """Add a user to the workspace.

    Requires: admin or owner role.
    """
    member = await service.invite_member(
        ctx.workspace.slug, data, actor_id=ctx.user.id
    )
    return WorkspaceMemberResponse.model_validate(member)


@router.patch(
    "/{slug}/members/{user_id}",
    response_model=WorkspaceMemberResponse,
)
async def update_member_role(
    user_id: uuid.UUID,
    data: MemberRoleUpdate,
    ctx: WorkspaceOwnerCtx,
    service: WorkspaceServiceDep,
) -> WorkspaceMemberResponse:
    """Change a member's role.

    Requires: owner role.
    """
    member = await service.update_member_role(
        ctx.workspace.slug, target_user_id=user_id, data=data, actor_id=ctx.user.id
    )
    return WorkspaceMemberResponse.model_validate(member)


@router.delete(
    "/{slug}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    user_id: uuid.UUID,
    ctx: WorkspaceMemberCtx,
    service: WorkspaceServiceDep,
) -> None:
    """Remove a member from the workspace.

    Requires: member role (members can remove themselves), admin or owner to remove others.
    """
    await service.remove_member(
        ctx.workspace.slug, target_user_id=user_id, actor_id=ctx.user.id
    )
