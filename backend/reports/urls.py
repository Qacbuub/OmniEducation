from django.urls import path

from . import views

urlpatterns = [
    path("schools/dashboard/", views.SchoolDashboardView.as_view(), name="school-dashboard"),
    path("universities/dashboard/", views.UniversityDashboardView.as_view(), name="university-dashboard"),
    path("students/<int:pk>/documents/id-card/", views.StudentIdCardView.as_view(), name="student-id-card"),
    path("students/<int:pk>/documents/enrollment-letter/", views.EnrollmentLetterView.as_view(),
         name="student-enrollment-letter"),
]
