from django.apps import AppConfig


class PeopleConfig(AppConfig):
    name = "people"
    verbose_name = "People: students, guardians, staff"

    def ready(self):
        from . import signals  # noqa: F401
