import os

from django.conf import settings
from django.core.files.base import ContentFile
from rest_framework.exceptions import ValidationError

from core.emails import send_notification_email
from core.models import User

from .models import Document, Notification


def notify(users, title, body="", *, kind="general", link="", email=False):
    """Create in-app notifications (and optionally emails) for users of one tenant."""
    created = []
    for user in users:
        if user is None or not user.is_active or not user.tenant_id:
            continue
        created.append(Notification(tenant_id=user.tenant_id, user=user, title=title, body=body, kind=kind, link=link))
        if email:
            send_notification_email(user, title, body)
    Notification.objects.bulk_create(created)
    return created


def notify_permission_holders(tenant, permission_code, title, body="", **kw):
    users = User.objects.filter(tenant=tenant, is_active=True, role__permissions__code=permission_code).distinct()
    return notify(users, title, body, **kw)


def validate_upload(f):
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in settings.DOCUMENT_ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(settings.DOCUMENT_ALLOWED_EXTENSIONS))
        raise ValidationError({"file": [f"File type {ext or '(none)'} is not allowed. Use {allowed}."]})
    if f.size > settings.DOCUMENT_MAX_BYTES:
        raise ValidationError({"file": [f"Files must be under {settings.DOCUMENT_MAX_BYTES // (1024 * 1024)} MB."]})
    return f


def save_generated_pdf(*, tenant, kind, title, pdf_bytes, student=None, user=None):
    doc = Document(tenant=tenant, kind=kind, title=title, student=student, generated=True, uploaded_by=user,
                   original_name=f"{title}.pdf", size=len(pdf_bytes))
    doc.file.save(f"{kind}.pdf", ContentFile(pdf_bytes), save=False)
    doc.save()
    return doc
