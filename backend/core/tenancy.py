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


def delete_tenant(tenant):
    """Permanently delete an institution and every row that belongs to it.

    Rows are removed model by model; a model whose rows are still protected by another model's rows (e.g. a
    student with invoices) is retried after the others, so the order follows the data instead of a hand list.
    Returns {model label: rows deleted}. Runs inside the caller's transaction.
    """
    from django.apps import apps
    from django.db import transaction
    from django.db.models import ProtectedError

    from .models import Tenant

    owned = [m for m in apps.get_models()
             if any(getattr(f, "related_model", None) is Tenant and f.name == "tenant" for f in m._meta.fields)]
    counts, remaining = {}, owned
    while remaining:
        blocked = []
        for model in remaining:
            try:
                with transaction.atomic():
                    deleted, per_model = model._base_manager.filter(tenant=tenant).delete()
                for label, n in per_model.items():
                    counts[label] = counts.get(label, 0) + n
            except ProtectedError:
                blocked.append(model)
        if len(blocked) == len(remaining):
            raise ProtectedError("Some records could not be deleted.", set())
        remaining = blocked
    tenant.delete()
    return {k: v for k, v in counts.items() if v}
