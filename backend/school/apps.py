from django.apps import AppConfig


class SchoolConfig(AppConfig):
    name = "school"
    verbose_name = "School (K-12): classes, attendance, marks, report cards, promotion"

    def ready(self):
        from . import hooks  # noqa: F401  (registers admissions, scoping, dashboard and seed hooks)
