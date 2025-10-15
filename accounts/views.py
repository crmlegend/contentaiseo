from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.contrib.auth.views import LoginView

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from rest_framework_simplejwt.tokens import RefreshToken

from billing.models import ApiKey
from .serializers import RegisterSerializer
from .forms import SignUpForm, NiceLoginForm, ProfileForm, DashboardPasswordChangeForm
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

# ---------------------------
# Public pages
# ---------------------------
def home(request):
    return render(request, "home.html")

# ---------------------------
# Auth pages (login/signup)
# ---------------------------
class NiceLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = NiceLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy("dashboard")

class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("login")  # after signup, go to login

# ---------------------------
# API (optional)
# ---------------------------
@api_view(["POST", "GET"])
@permission_classes([AllowAny])
def register(request):
    s = RegisterSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    s.save()
    return Response({"ok": True})

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    u = request.user
    return Response({
        "id": u.id,
        "email": u.email,
        "stripe_customer_id": getattr(u, "stripe_customer_id", None)
    })

@login_required
def dashboard(request):
    user = request.user

    # ----- Profile / password forms -----
    profile_form = ProfileForm(instance=user)
    pwd_form = DashboardPasswordChangeForm(user=user)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "update_profile":
            profile_form = ProfileForm(request.POST, instance=user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated.")
                return redirect("dashboard")

        elif action == "change_password":
            pwd_form = DashboardPasswordChangeForm(user=user, data=request.POST)
            if pwd_form.is_valid():
                pwd_form.save()
                messages.success(request, "Password changed.")
                return redirect("dashboard")

    # ----- Short-lived JWT for your JS calls -----
    access = str(RefreshToken.for_user(user).access_token)

    # ----- API key lookup (matches your billing view logic) -----
    uid_str = str(user.id)
    cust_id = getattr(user, "stripe_customer_id", None)

    q = Q(user=user) | Q(tenant_id=uid_str)
    if cust_id:
        q |= Q(customer_id=cust_id) | Q(tenant_id=cust_id)

    key_row = (
        ApiKey.objects
        .filter(q, status="active", revoked_at__isnull=True)
        .order_by("-created_at")
        .first()
    )

    # Full key only if you actually store a plain suffix
    full_key = None
    latest_key_prefix = None
    if key_row:
        latest_key_prefix = key_row.key_prefix
        suffix = getattr(key_row, "plain_suffix", None)
        if suffix:                           # only build if suffix exists
            full_key = f"{key_row.key_prefix or ''}{suffix}"

    # ----- Trial usage & plan status -----
    trial_used = None
    trial_quota = None
    is_trial = False
    is_subscribed = False
    if key_row:
        if key_row.plan == "trial":
            is_trial = True
            # used_requests increments with each API call
            trial_used = key_row.used_requests or 0
            trial_quota = key_row.trial_quota or 0
        else:
            is_subscribed = True

    # ----- Context for your template -----
    return render(request, "dashboard.html", {
        "access": access,
        "profile_form": profile_form,
        "pwd_form": pwd_form,

        # KPI cards / other blocks
        "key": key_row,
        "latest_key_prefix": latest_key_prefix,

        # The block that prints {{ cd }} expects this name:
        "cd": full_key,
        "raw_api_key": full_key,

        # Trial and subscription data
        "is_trial": is_trial,
        "is_subscribed": is_subscribed,
        "trial_used": trial_used,
        "trial_quota": trial_quota,
    })

# ---------------------------
# profile_update (for your /profile/update URL)
# ---------------------------
@login_required
def profile_update(request):
    """
    Minimal handler so core/urls.py -> acc_views.profile_update works.
    We process POST (update profile) and always redirect back to dashboard.
    GET simply redirects to the dashboard where the form already lives.
    """
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
        else:
            messages.error(request, "Please correct the errors and try again.")
    return redirect("dashboard")
