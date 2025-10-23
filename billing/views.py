# billing/views.py
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.conf import settings
from django.utils import timezone

import logging
import stripe

from .models import ApiKey  # and WebhookEvent if you decide to log events
from .utils import verify_token_in_db
from .utils import activate_paid_plan_for_user  # <-- use this to flip trial -> pro

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY
User = get_user_model()

# Event types on which we consider the subscription "active/paid"
ACTIVE_EVENTS = {
    "checkout.session.completed",
    "invoice.paid",
    "customer.subscription.updated",
}

# ---------- Public API ----------

@api_view(["POST"])
@permission_classes([AllowAny])
def verify_key(request):
    """
    POST: {"key":"<raw api key>"}
    200 -> {"ok": true, "plan": "...", "key_prefix": "..."}
    401 -> {"ok": false}
    """
    raw = (request.data or {}).get("key", "")
    raw = (raw or "").strip()

    row = verify_token_in_db(raw)
    if not row:
        return Response({"ok": False}, status=401)

    return Response({
        "ok": True,
        "plan": row.plan,
        "key_prefix": row.key_prefix,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_checkout(request):
    """
    Create a Stripe Checkout Session for subscription.
    Ensures the user has a Stripe customer id, then starts a subscription checkout.
    """
    user: User = request.user

    # Ensure Stripe customer exists and is linked to the user
    if not getattr(user, "stripe_customer_id", None):
        cust = stripe.Customer.create(
            email=user.email or None,
            metadata={"django_user_id": user.id},
        )
        user.stripe_customer_id = cust.id
        user.save(update_fields=["stripe_customer_id"])

    site = request.data.get("site") or "https://contentseoai-c2ahaybrcha9hkcw.canadacentral-01.azurewebsites.net/"
    success_url = f"{site}/accounts/dashboard/?sub=success"
    cancel_url  = f"{site}/accounts/dashboard/?sub=cancel"

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=user.stripe_customer_id,
        line_items=[{"price": settings.STRIPE_PRICE_ID, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
    )

    return Response({"url": session.url})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_key(request):
    """
    Return the user's active key prefix and issue date (never the raw key).
    """
    row = (
        ApiKey.objects
        .filter(user=request.user, status="active", revoked_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if not row:
        return Response({"ok": False, "key": None})
    return Response({"ok": True, "key_prefix": row.key_prefix, "issued_at": row.created_at.isoformat()})


# ---------- Webhooks ----------

@csrf_exempt
def stripe_webhook(request):
    """
    Verify Stripe signature and flip the user to a paid plan when appropriate.
    We handle multiple events to be robust:
      - checkout.session.completed
      - invoice.paid
      - customer.subscription.updated (only if status == 'active')
    Always ACK quickly with 200 on success to avoid Stripe retries.
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    secret = settings.STRIPE_WEBHOOK_SECRET

    # 1) Verify signature
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception as e:
        logger.warning("Stripe webhook verification failed: %s", e)
        return HttpResponse(status=400)

    evt_type = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}

    if evt_type in ACTIVE_EVENTS:
        # For subscription.updated, check it's actually active
        if evt_type == "customer.subscription.updated":
            if (obj.get("status") or "").lower() != "active":
                return HttpResponse(status=200)

        customer_id = obj.get("customer")

        # Try to find the user by customer_id (primary)
        user = None
        if customer_id:
            user = User.objects.filter(stripe_customer_id=customer_id).first()

        # Fallback: try by email if present on the object
        if not user:
            email = (obj.get("customer_details") or {}).get("email") \
                    or obj.get("customer_email") \
                    or obj.get("email")
            if email:
                user = User.objects.filter(email__iexact=email).first()

        try:
            if user:
                # Flip to paid (rotate key to avoid keeping the trial token alive)
                activate_paid_plan_for_user(user=user, customer_id=customer_id, rotate_key=True)
                logger.info("Upgraded to paid: user_id=%s customer=%s evt=%s", user.id, customer_id, evt_type)
            else:
                logger.warning("Webhook: no mapped user for customer=%s (evt=%s)", customer_id, evt_type)
        except Exception as e:
            # Don't fail the webhook; log and ack to prevent retries loop
            logger.exception("Webhook processing error: %s", e)

    return HttpResponse(status=200)
