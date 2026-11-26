from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


def health(request):
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


api = [
    path("", include("core.urls")),
    path("", include("people.urls")),
    path("", include("admissions.urls")),
    path("", include("finance.urls")),
    path("", include("comms.urls")),
    path("", include("reports.urls")),
    path("schools/", include("school.urls")),
    path("universities/", include("university.urls")),
    path("health/", health, name="health"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
    path("redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(api)),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    # Only tenant logos are public; documents are always served through the permission-checked API.
    urlpatterns += static(settings.MEDIA_URL + "tenant-logos/", document_root=settings.MEDIA_ROOT / "tenant-logos")
