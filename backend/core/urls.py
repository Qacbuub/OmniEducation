from django.urls import path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

router = SimpleRouter()
router.register("tenants", views.TenantViewSet, basename="tenant")
router.register("invitations", views.InvitationViewSet, basename="invitation")
router.register("users", views.StaffUserViewSet, basename="user")

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/token/fork/", views.TokenForkView.as_view(), name="token-fork"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("auth/password-reset/", views.PasswordResetRequestView.as_view(), name="password-reset"),
    path("auth/password-reset/confirm/", views.PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("auth/invitations/accept/", views.InvitationAcceptView.as_view(), name="invitation-accept"),
    path("auth/invitations/<str:token>/", views.InvitationLookupView.as_view(), name="invitation-lookup"),
    path("auth/mfa/", views.MfaSetupView.as_view(), name="mfa-setup"),
    path("auth/password/", views.ChangePasswordView.as_view(), name="password-change"),
    path("tenants/current/", views.CurrentTenantView.as_view(), name="tenant-current"),
    path("platform/stats/", views.PlatformStatsView.as_view(), name="platform-stats"),
    path("platform/invitations/", views.PlatformInvitationListView.as_view(), name="platform-invitations"),
    path("platform/invitations/<int:pk>/", views.PlatformInvitationDetailView.as_view(),
         name="platform-invitation-detail"),
    path("platform/audit/", views.PlatformAuditView.as_view(), name="platform-audit"),
    path("audit/", views.AuditLogView.as_view(), name="audit"),
    *router.urls,
]
