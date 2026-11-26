from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("faculties", views.FacultyViewSet, basename="uni-faculty")
router.register("departments", views.DepartmentViewSet, basename="uni-department")
router.register("programs", views.ProgramViewSet, basename="uni-program")
router.register("courses", views.CourseViewSet, basename="uni-course")
router.register("prerequisites", views.PrerequisiteViewSet, basename="uni-prerequisite")
router.register("curricula", views.CurriculumViewSet, basename="uni-curriculum")
router.register("curriculum-courses", views.CurriculumCourseViewSet, basename="uni-curriculum-course")
router.register("semesters", views.SemesterViewSet, basename="uni-semester")
router.register("offerings", views.OfferingViewSet, basename="uni-offering")
router.register("registrations", views.RegistrationViewSet, basename="uni-registration")
router.register("assessments", views.AssessmentViewSet, basename="uni-assessment")
router.register("grades", views.GradeViewSet, basename="uni-grade")
router.register("standings", views.StandingViewSet, basename="uni-standing")
router.register("clearances", views.ClearanceViewSet, basename="uni-clearance")

urlpatterns = [
    path("catalog-stats/", views.CatalogStatsView.as_view(), name="uni-catalog-stats"),
    path("grade-approvals/", views.GradeApprovalQueueView.as_view(), name="uni-grade-approvals"),
    path("timetable/", views.TimetableView.as_view(), name="uni-timetable"),
    path("transcripts/<str:student_id>/", views.TranscriptView.as_view(), name="uni-transcript"),
    path("transcripts/<str:student_id>/pdf/", views.TranscriptPdfView.as_view(), name="uni-transcript-pdf"),
    path("degree-audit/<str:student_id>/", views.DegreeAuditView.as_view(), name="uni-degree-audit"),
    *router.urls,
]
