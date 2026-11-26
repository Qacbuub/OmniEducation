from django.apps import AppConfig


class UniversityConfig(AppConfig):
    name = "university"
    verbose_name = "University: programs, courses, registration, grades, transcripts"

    def ready(self):
        from . import hooks  # noqa: F401  (registers admissions, scoping, dashboard and seed hooks)
