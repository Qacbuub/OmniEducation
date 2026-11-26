from django.contrib import admin

from .models import EmergencyContact, Guardian, GuardianLink, Person, Staff, Student

for m in (Person, Student, Guardian, GuardianLink, EmergencyContact, Staff):
    admin.site.register(m)
