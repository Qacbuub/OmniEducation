"""Outgoing email. Development uses the console backend, so messages are printed to the terminal."""
import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _send(to, subject, body):
    """Send one email. A mail-server problem never breaks the request; it is written to the server log."""
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to])
        return True
    except Exception:  # noqa: BLE001 - SMTP errors come in many types
        logger.exception("Could not send email %r to %s (check the EMAIL_* settings).", subject, to)
        return False


def emails_enabled():
    """False when the server only prints emails to its log (console/dummy backend) instead of sending them."""
    backend = settings.EMAIL_BACKEND
    return not (backend.endswith("console.EmailBackend") or backend.endswith("dummy.EmailBackend"))


def send_invitation(invitation):
    """Returns True when the email was really handed to the mail server."""
    institution = invitation.tenant.name if invitation.tenant else "the OmniEducation platform"
    link = f"{settings.FRONTEND_URL}/accept-invitation?token={invitation.token}"
    return emails_enabled() and _send(
        invitation.email,
        f"You're invited to {institution} on OmniEducation",
        f"Hello,\n\nYou have been invited to join {institution} as {invitation.role.name}.\n"
        f"Set your password here (link valid for 7 days):\n{link}\n\nOmniEducation by OmniTeckno",
    )


def send_password_reset(user, uid, token):
    link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
    _send(
        user.email,
        "Reset your OmniEducation password",
        f"Hello {user.first_name or ''},\n\nUse this single-use link to reset your password. "
        f"It expires in 1 hour:\n{link}\n\nIf you didn't ask for this, you can ignore this email.",
    )


def send_notification_email(user, title, body):
    _send(user.email, title, body)
