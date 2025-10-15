from rest_framework.permissions import BasePermission

class IsSubscriber(BasePermission):
    def has_permission(self, request, view):
        ctx = request.auth  # set by ApiKeyAuthentication
        # Allow paying customers + trials (quota enforced in auth)
        return bool(ctx) and ctx.get("plan") in {"pro", "team", "trial"}
