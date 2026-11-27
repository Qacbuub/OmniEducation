from .models import AuditEvent


def client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None


def log_event(action, *, request=None, actor=None, tenant=None, target=None, changes=None):
    """Write one audit event. `target` can be any model instance."""
    actor = actor or (request.user if request is not None and request.user.is_authenticated else None)
    if tenant is None:
        tenant = getattr(target, "tenant", None) or getattr(actor, "tenant", None)
    return AuditEvent.objects.create(
        tenant=tenant,
        actor=actor,
        actor_email=getattr(actor, "email", "") or "",
        action=action,
        target_type=target._meta.label_lower if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        target_repr=str(target)[:255] if target is not None else "",
        changes=changes or {},
        ip_address=client_ip(request),
    )


def delete_reason(request):
    """The optional reason someone gave when deleting a record (sent in the DELETE body), for the audit log."""
    try:
        data = request.data
    except Exception:  # noqa: BLE001 - an unreadable body just means no reason
        return ""
    return str(data.get("reason", "") if hasattr(data, "get") else "").strip()[:300]
