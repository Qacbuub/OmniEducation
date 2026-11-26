from django.contrib import admin

from . import models

for m in (models.GradeLevel, models.Subject, models.ClassSection, models.ClassAssignment, models.ClassPlacement,
          models.SchoolTimetable, models.PupilAttendance, models.SchoolAssessment, models.SchoolMark,
          models.TermResult, models.PromotionDecision):
    admin.site.register(m)
