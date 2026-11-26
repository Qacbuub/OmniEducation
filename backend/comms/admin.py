from django.contrib import admin

from .models import Announcement, Document, Notification

for m in (Notification, Announcement, Document):
    admin.site.register(m)
