from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.core.permissions import WorkspaceAdminCtx, WorkspaceMemberCtx
from app.core.rate_limit import WorkspaceRateLimit
from app.repositories.subscription import SubscriptionRepository
from app.repositories.user import UserRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.subscription import (
    BillingSetupResponse,
    CheckoutRequest,
    CheckoutResponse,
    SubscriptionResponse,
)
from app.services.subscription import SubscriptionService
from app.services.workspace import WorkspaceService

router = APIRouter(tags=["billing"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


def _get_subscription_service(session: SessionDep) -> SubscriptionService:
    return SubscriptionService(sub_repo=SubscriptionRepository(session))


def _get_workspace_service(session: SessionDep) -> WorkspaceService:
    return WorkspaceService(
        workspace_repo=WorkspaceRepository(session),
        user_repo=UserRepository(session),
    )


SubscriptionServiceDep = Annotated[
    SubscriptionService, Depends(_get_subscription_service)
]
WorkspaceServiceDep = Annotated[WorkspaceService, Depends(_get_workspace_service)]


@router.post(
    "/workspaces/{slug}/billing/setup",
    response_model=BillingSetupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def setup_billing(
    ctx: WorkspaceAdminCtx,
    current_user: CurrentUser,
    service: SubscriptionServiceDep,
    _: WorkspaceRateLimit,
) -> BillingSetupResponse:
    """Create a Stripe customer for the workspace if one does not exist yet.

    Requires: admin or owner role.
    """
    sub = await service.get_or_create_customer(
        workspace_id=ctx.workspace.id,
        workspace_name=ctx.workspace.name,
        owner_email=current_user.email,
    )
    return BillingSetupResponse.model_validate(sub)


@router.post(
    "/workspaces/{slug}/billing/checkout",
    response_model=CheckoutResponse,
)
async def create_checkout(
    data: CheckoutRequest,
    ctx: WorkspaceAdminCtx,
    service: SubscriptionServiceDep,
    _: WorkspaceRateLimit,
) -> CheckoutResponse:
    """Create a Stripe Checkout session and return the hosted URL.

    Requires: admin or owner role.
    """
    url = await service.create_checkout_session(
        workspace_id=ctx.workspace.id,
        success_url=str(data.success_url),
        cancel_url=str(data.cancel_url),
    )
    return CheckoutResponse(url=url)


@router.get(
    "/workspaces/{slug}/billing",
    response_model=SubscriptionResponse,
)
async def get_billing(
    ctx: WorkspaceMemberCtx,
    service: SubscriptionServiceDep,
    _: WorkspaceRateLimit,
) -> SubscriptionResponse:
    """Get the current subscription status for a workspace.

    Requires: member, admin, or owner role.
    """
    sub = await service.sub_repo.get_by_workspace_id(ctx.workspace.id)
    if not sub:
        raise NotFoundError("Subscription")
    return SubscriptionResponse.model_validate(sub)


@router.post("/billing/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    service: SubscriptionServiceDep,
    stripe_signature: Annotated[str, Header(alias="stripe-signature")] = "",
) -> dict[str, str]:
    """Receive and process Stripe webhook events.

    No authentication — Stripe signature is verified inside the service.
    """
    payload = await request.body()
    await service.handle_webhook(payload=payload, sig_header=stripe_signature)
    return {"status": "ok"}
