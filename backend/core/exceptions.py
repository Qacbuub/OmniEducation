"""Every API error is returned as {"code", "message", "fields"} so the frontend can show it consistently."""
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler


class BusinessRuleViolation(exceptions.APIException):
    """A request that is well-formed but breaks an institutional rule (e.g. course is full)."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "business_rule"
    default_detail = "This action is not allowed by institution policy."

    def __init__(self, message, code="business_rule", fields=None):
        super().__init__(detail=message, code=code)
        self.rule_code = code
        self.fields = fields or {}


def _flatten(detail):
    if isinstance(detail, dict):
        return {k: _flatten(v) for k, v in detail.items()}
    if isinstance(detail, list):
        return [str(d) if not isinstance(d, (dict, list)) else _flatten(d) for d in detail]
    return [str(detail)]


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, BusinessRuleViolation):
        body = {"code": exc.rule_code, "message": str(exc.detail), "fields": exc.fields}
    elif isinstance(exc, exceptions.ValidationError):
        fields = _flatten(exc.detail) if isinstance(exc.detail, dict) else {}
        non_field = fields.pop("non_field_errors", None) if fields else None
        if isinstance(exc.detail, list):
            non_field = _flatten(exc.detail)
        message = non_field[0] if non_field else "Please correct the highlighted fields."
        body = {"code": "validation_error", "message": message, "fields": fields}
    else:
        detail = exc.detail if hasattr(exc, "detail") else str(exc)
        code = getattr(detail, "code", None) or getattr(exc, "default_code", "error")
        body = {"code": code, "message": str(detail), "fields": {}}

    headers = {h: response[h] for h in ("WWW-Authenticate", "Retry-After") if response.has_header(h)}
    return Response(body, status=response.status_code, headers=headers)
