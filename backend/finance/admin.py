from django.contrib import admin

from .models import FeePlan, FeePlanItem, Invoice, InvoiceLine, Payment

for m in (FeePlan, FeePlanItem, Invoice, InvoiceLine, Payment):
    admin.site.register(m)
