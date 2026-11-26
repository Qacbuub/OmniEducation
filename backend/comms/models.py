import os
import uuid

from django.conf import settings
from django.db import models

from core.models import TenantScopedModel


class Notification(TenantScopedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    kind = models.CharField(max_length=40, default="general")  # e.g. attendance, admission, grade, fee
    link = models.CharField(max_length=255, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at"])]


class Announcement(TenantScopedModel):
    title = models.CharField(max_length=200)
    body = models.TextField()
    # Empty list = everyone in the institution; otherwise role codes, e.g. ["guardian", "class_teacher"].
    audience_roles = models.JSONField(default=list, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    pinned = models.BooleanField(default=False)

    class Meta:
        ordering = ["-pinned", "-created_at"]

    def __str__(self):
        return self.title


def document_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    # Random names: files are never guessable, and are only served through the permission-checked API.
    return f"documents/{instance.tenant_id}/{uuid.uuid4().hex}{ext}"


class Document(TenantScopedModel):
    class Kind(models.TextChoices):
        SUPPORTING = "supporting", "Supporting document"
        BIRTH_CERTIFICATE = "birth_certificate", "Birth certificate"
        PREVIOUS_RESULTS = "previous_results", "Previous results"
        ID_CARD = "id_card", "Student ID card"
        ENROLLMENT_LETTER = "enrollment_letter", "Enrollment letter"
        REPORT_CARD = "report_card", "Report card"
        TRANSCRIPT = "transcript", "Transcript"
        RECEIPT = "receipt", "Receipt"
        OTHER = "other", "Other"

    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.SUPPORTING)
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to=document_path)
    original_name = models.CharField(max_length=255, blank=True)
    size = models.PositiveIntegerField(default=0)
    student = models.ForeignKey("people.Student", null=True, blank=True, on_delete=models.CASCADE,
                                related_name="documents")
    application = models.ForeignKey("admissions.Application", null=True, blank=True, on_delete=models.CASCADE,
                                    related_name="documents")
    generated = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
