from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("grade-levels", views.GradeLevelViewSet, basename="school-grade-level")
router.register("subjects", views.SubjectViewSet, basename="school-subject")
router.register("classes", views.SectionViewSet, basename="school-class")
router.register("allocations", views.AssignmentViewSet, basename="school-allocation")
router.register("placements", views.PlacementViewSet, basename="school-placement")
router.register("timetable", views.TimetableViewSet, basename="school-timetable")
router.register("attendance", views.AttendanceViewSet, basename="school-attendance")
router.register("assessments", views.AssessmentViewSet, basename="school-assessment")
router.register("results", views.TermResultViewSet, basename="school-result")
router.register("promotions", views.PromotionViewSet, basename="school-promotion")

urlpatterns = [
    path("children/", views.ChildrenView.as_view(), name="school-children"),
    *router.urls,
]
