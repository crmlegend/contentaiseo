
# core/urls.py
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts import views as acc_views
from content import views as content_views
from billing import views as bill_views
# NOTE: billing views are routed via billing/urls.py – no need to import them here

# accounts/views.py (or another appropriate file)
from django.shortcuts import render

def home(request):
    """Renders the home.html page."""
    # Django will look for 'home.html' inside the 'templates' directory
    return render(request, 'home.html')

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # Landing
    path("", home, name="home"),

    # Accounts (your app + Django auth)
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("django.contrib.auth.urls")),

    # Auth API (JWT + register + profile)
    path("auth/login", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/register", acc_views.register, name="auth_register"),
    path("users/me", acc_views.me, name="users_me"),

    # Billing: include all billing routes (start, webhook, key, verify, test)
    path("billing/", include("billing.urls")),   # -> /billing/start/, /billing/webhook/, /billing/key/, /billing/verify/

    # (Optional legacy aliases — keep only if clients already use these)
    path("api/key/verify/", bill_views.verify_key, name="api_key_verify"),
    # path("v1/billing/checkout", bill_views.start_checkout, name="start_checkout_legacy"),
    # path("v1/keys/mine", bill_views.my_key, name="my_key_legacy"),

    # Product API (guarded by ApiKeyAuthentication for /v1/*)
    path("v1/generate/content", content_views.generate, name="generate_content"),
    path("v1/blog/preview", content_views.blog_preview, name="blog_preview"),
]




