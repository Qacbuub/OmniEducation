from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_roles(sender, **kwargs):
    from .rbac import sync_roles

    sync_roles()


class CoreConfig(AppConfig):
    name = "core"
    verbose_name = "Core: tenants, identity, roles, audit"

    def ready(self):
        post_migrate.connect(_sync_roles, sender=self)
