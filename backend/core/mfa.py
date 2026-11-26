"""Time-based one-time passwords (RFC 6238), compatible with Google Authenticator / Authy.

MFA is optional per user (User.mfa_enabled). When enabled, login requires a valid 6-digit code.
Implemented with the standard library so there is no extra dependency.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret, counter):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def totp_now(secret, at=None):
    return _code(secret, int((at or time.time()) // 30))


def verify(secret, code, window=1):
    """Accept the current code and one step either side to allow for clock drift."""
    if not secret or not code or not str(code).isdigit():
        return False
    counter = int(time.time() // 30)
    return any(hmac.compare_digest(_code(secret, counter + d), str(code)) for d in range(-window, window + 1))


def provisioning_uri(secret, email, issuer="OmniEducation"):
    return f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}"
