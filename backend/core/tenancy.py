"""
Server-side tenant isolation.

* Every tenant-owned queryset is filtered by request.user.tenant, so another tenant's record
  is simply not found (404), never "forbidden but exists".
* The tenant is always taken from the authenticated user, never from the request body.
* Related-object fields only accept IDs from the same tenant.
"""
import datetime
import decimal

from django.db import models
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated

from .audit import log_event
from .permissions import IsTenantUser, RolePermission


def jsonable(value):
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, models.Model):
        return value.pk
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time, decimal.Decimal)):
        return str(value)
    if hasattr(value, "name") and hasattr(value, "read"):  # uploaded file
        return value.name
    return value


class TenantPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """A foreign-key field that only accepts objects belonging to the requester's tenant."""

    def get_queryset(self):
        qs = super().get_queryset()
        if not any(f.name == "tenant" for f in qs.model._meta.get_fields()):
            return qs
        tenant = self.context.get("tenant")  # set explicitly for public (anonymous) endpoints
        if tenant is None:
            request = self.context.get("request")
            if request is None or not request.user.is_authenticated or not request.user.tenant_id:
                return qs.none()
            tenant = request.user.tenant
        return qs.filter(tenant=tenant)


class TenantModelSerializer(serializers.ModelSerializer):
    """ModelSerializer whose auto-generated foreign-key fields are tenant-restricted."""

    serializer_related_field = TenantPrimaryKeyRelatedField


class TenantScopedViewSetMixin:
    """Mixin for ModelViewSets over TenantScopedModel subclasses."""

    permission_classes = [IsAuthenticated, IsTenantUser, RolePermission]
    audit_name = None  # e.g. "student" → audit actions "student.created", ...

    @property
    def tenant(self):
        return self.request.user.tenant

    def get_queryset(self):
        return super().get_queryset().filter(tenant=self.request.user.tenant)

    def _audit_name(self):
        return self.audit_name or self.get_queryset().model._meta.model_name

    def perform_create(self, serializer):
        obj = serializer.save(tenant=self.tenant)
        log_event(f"{self._audit_name()}.created", request=self.request, target=obj,
                  changes=jsonable(serializer.validated_data))

    def perform_update(self, serializer):
        obj = serializer.save()
        log_event(f"{self._audit_name()}.updated", request=self.request, target=obj,
                  changes=jsonable(serializer.validated_data))

    def perform_destroy(self, instance):
        log_event(f"{self._audit_name()}.deleted", request=self.request, target=instance)
        instance.delete()
