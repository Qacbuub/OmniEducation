from .base import *  # noqa: F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests only
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"login": "1000/min", "password_reset": "1000/min", "password_change": "1000/min", "anon": "1000/min"}}  # noqa: F405
