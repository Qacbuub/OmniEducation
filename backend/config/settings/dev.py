from .base import *  # noqa: F401,F403
from .base import env_bool

DEBUG = env_bool("DJANGO_DEBUG", True)
# On a development machine, always show invitation links on screen as well, even when real email is set up,
# so a failed or slow email never blocks testing.
SHOW_INVITE_LINKS = env_bool("SHOW_INVITE_LINKS", True)
