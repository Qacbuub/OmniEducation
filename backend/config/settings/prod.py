"""Production settings: served by Gunicorn behind Nginx with HTTPS."""
from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env_bool, env_list

DEBUG = False
if not SECRET_KEY or SECRET_KEY.startswith(("insecure", "CHANGE-ME")):
    raise RuntimeError("Set DJANGO_SECRET_KEY in the environment for production.")

# Origins allowed to post forms to Django itself (the /admin/ login), e.g. https://omniedu.example.com
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

# Nginx terminates TLS and forwards the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
# Cookies only travel over HTTPS. Set DJANGO_SECURE_COOKIES=false only for a local plain-HTTP deployment.
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30 if SECURE_SSL_REDIRECT else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
