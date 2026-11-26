from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("students", views.StudentViewSet, basename="student")
router.register("guardians", views.GuardianViewSet, basename="guardian")
router.register("guardian-links", views.GuardianLinkViewSet, basename="guardian-link")
router.register("emergency-contacts", views.EmergencyContactViewSet, basename="emergency-contact")
router.register("staff", views.StaffViewSet, basename="staff")
urlpatterns = router.urls
