from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("academic-periods", views.AcademicPeriodViewSet, basename="academic-period")
router.register("admissions", views.ApplicationViewSet, basename="application")
router.register("enrollments", views.EnrollmentViewSet, basename="enrollment")

urlpatterns = [
    path("public/<slug:slug>/apply/", views.PublicApplicationView.as_view(), name="public-apply"),
    path("public/<slug:slug>/applications/<str:reference>/", views.PublicApplicationStatusView.as_view(),
         name="public-application-status"),
    path("public/<slug:slug>/applications/<str:reference>/documents/", views.PublicApplicationDocumentView.as_view(),
         name="public-application-documents"),
    *router.urls,
]
