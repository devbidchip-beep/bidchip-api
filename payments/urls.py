from django.urls import path

from payments.views import (
    CheckoutView,
    StripeConnectOnboardView,
    StripeConnectReturnView,
)
from payments.webhooks import stripe_webhook

urlpatterns = [
    path("checkout/", CheckoutView.as_view()),
    path("stripe/connect/", StripeConnectOnboardView.as_view()),
    path("stripe/connect/return/", StripeConnectReturnView.as_view()),
    path("stripe/webhook/", stripe_webhook),
]
