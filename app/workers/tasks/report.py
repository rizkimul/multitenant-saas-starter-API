import asyncio
import uuid
from typing import Any

from sqlalchemy import func, select

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="report.generate_workspace_report",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)  # type: ignore[untyped-decorator]
def generate_workspace_report(self: Any, workspace_id: str) -> dict[str, Any]:
    """Generate a usage summary report for a workspace.

    Queries member counts by role, subscription status, and packages
    the result as a dict. Extend to email or store the report as needed.

    Args:
        workspace_id: UUID string of the target workspace.

    Returns:
        Report dict with member breakdown and subscription info.
    """
    try:
        report = asyncio.run(_build_report(uuid.UUID(workspace_id)))
        logger.info("Workspace report generated", extra={"workspace_id": workspace_id})
        return report
    except Exception as exc:
        logger.error(
            "Failed to generate workspace report",
            extra={"workspace_id": workspace_id, "error": str(exc)},
        )
        raise self.retry(exc=exc)


async def _build_report(workspace_id: uuid.UUID) -> dict[str, Any]:
    """Fetch workspace data and assemble the report.

    Args:
        workspace_id: The workspace UUID.

    Returns:
        Structured report dict.

    Raises:
        ValueError: If the workspace does not exist.
    """
    async with AsyncSessionLocal() as session:
        workspace = await session.get(Workspace, workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        role_counts_result = await session.execute(
            select(WorkspaceMember.role, func.count(WorkspaceMember.user_id))
            .where(WorkspaceMember.workspace_id == workspace_id)
            .group_by(WorkspaceMember.role)
        )
        role_counts: dict[str, int] = {
            role.value: count for role, count in role_counts_result.all()
        }

        sub_result = await session.execute(
            select(Subscription).where(Subscription.workspace_id == workspace_id)
        )
        sub = sub_result.scalars().first()

        return {
            "workspace_id": str(workspace_id),
            "workspace_name": workspace.name,
            "members": {
                "total": sum(role_counts.values()),
                "by_role": {
                    WorkspaceRole.owner.value: role_counts.get(
                        WorkspaceRole.owner.value, 0
                    ),
                    WorkspaceRole.admin.value: role_counts.get(
                        WorkspaceRole.admin.value, 0
                    ),
                    WorkspaceRole.member.value: role_counts.get(
                        WorkspaceRole.member.value, 0
                    ),
                },
            },
            "subscription": {
                "status": (
                    sub.status.value if sub else SubscriptionStatus.incomplete.value
                ),
                "stripe_customer_id": sub.stripe_customer_id if sub else None,
                "current_period_end": (
                    sub.current_period_end.isoformat()
                    if sub and sub.current_period_end
                    else None
                ),
                "cancel_at_period_end": sub.cancel_at_period_end if sub else False,
            },
        }
