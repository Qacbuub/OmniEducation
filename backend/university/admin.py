from django.contrib import admin

from . import models

for m in (models.Faculty, models.Department, models.Program, models.Course, models.CoursePrerequisite,
          models.Curriculum, models.CurriculumCourse, models.Semester, models.CourseOffering, models.OfferingMeeting,
          models.AcademicStanding, models.CourseRegistration, models.UniversityAssessment, models.UniversityGrade,
          models.GraduationClearance):
    admin.site.register(m)


@admin.register(models.TranscriptEntry, models.GradeApproval)
class ReadOnlyAdmin(admin.ModelAdmin):
    """Immutable history: viewable, never editable."""

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
