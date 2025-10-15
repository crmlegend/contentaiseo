# billing/urls.py
from django.urls import path
from .views import (
    start_checkout,
    stripe_webhook,
    my_key,
    # test_webhook,
    verify_key,        # <-- add this if you use the verify endpoint
)

app_name = "billing"   # optional but helpful for namespacing

urlpatterns = [
    path("start/", start_checkout, name="start_checkout"),   # create checkout session
    path("webhook/", stripe_webhook, name="stripe_webhook"), # payment provider webhook (Stripe)
    path("key/", my_key, name="my_key"),                     # show active key prefix to the logged-in user
    path("verify/", verify_key, name="verify_key"),          # verify a raw API key (public)
    # path("test/", test_webhook, name="test_webhook"),        # simple test endpoint
]
