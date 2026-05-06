from typing import Any

from app.core.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="email.send_welcome", bind=True, max_retries=3, default_retry_delay=60
)  # type: ignore[untyped-decorator]
def send_welcome_email(self: Any, user_id: str, email: str, name: str) -> dict[str, Any]:
    """Send a welcome email to a newly registered user.

    Args:
        user_id: UUID string of the new user.
        email: Recipient email address.
        name: Display name for personalisation.

    Returns:
        Dict with task result metadata.
    """
    try:
        logger.info("Sending welcome email", extra={"user_id": user_id, "email": email})

        # --- swap this block for real provider (SendGrid, SES, etc.) ---
        _send(
            to=email,
            subject="Welcome to SaaS Starter!",
            body=f"Hi {name},\n\nThanks for signing up. Your account is ready.\n",
        )
        # ----------------------------------------------------------------

        logger.info("Welcome email sent", extra={"user_id": user_id})
        return {"status": "sent", "user_id": user_id}

    except Exception as exc:
        logger.error(
            "Failed to send welcome email",
            extra={"user_id": user_id, "error": str(exc)},
        )
        raise self.retry(exc=exc)


@celery_app.task(
    name="email.send_subscription_confirmed",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)  # type: ignore[untyped-decorator]
def send_subscription_confirmed_email(
    self: Any, workspace_id: str, workspace_name: str, email: str
) -> dict[str, Any]:
    """Notify workspace owner that their subscription is now active.

    Args:
        workspace_id: UUID string of the workspace.
        workspace_name: Human-readable workspace name.
        email: Owner's email address.

    Returns:
        Dict with task result metadata.
    """
    try:
        logger.info(
            "Sending subscription confirmed email",
            extra={"workspace_id": workspace_id, "email": email},
        )

        _send(
            to=email,
            subject=f"Subscription active — {workspace_name}",
            body=(
                f"Hi,\n\nYour subscription for {workspace_name} is now active. "
                "Enjoy all features!\n"
            ),
        )

        logger.info("Subscription email sent", extra={"workspace_id": workspace_id})
        return {"status": "sent", "workspace_id": workspace_id}

    except Exception as exc:
        logger.error(
            "Failed to send subscription email",
            extra={"workspace_id": workspace_id, "error": str(exc)},
        )
        raise self.retry(exc=exc)


def _send(to: str, subject: str, body: str) -> None:
    """Stub email sender — replace with real provider integration.

    Args:
        to: Recipient address.
        subject: Email subject line.
        body: Plain-text email body.
    """
    logger.debug("EMAIL STUB", extra={"to": to, "subject": subject, "body": body})
