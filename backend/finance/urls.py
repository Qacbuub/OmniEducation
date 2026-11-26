from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("fees/plans", views.FeePlanViewSet, basename="fee-plan")
router.register("fees/invoices", views.InvoiceViewSet, basename="invoice")
router.register("fees/payments", views.PaymentViewSet, basename="payment")

urlpatterns = [path("fees/arrears/", views.ArrearsView.as_view(), name="arrears"), *router.urls]
