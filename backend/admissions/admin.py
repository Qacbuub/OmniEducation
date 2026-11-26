from django.contrib import admin

from .models import AcademicPeriod, Application, Enrollment

for m in (AcademicPeriod, Application, Enrollment):
    admin.site.register(m)
