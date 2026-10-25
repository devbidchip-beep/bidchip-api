"""
URL routing for the logistics app.
"""

from django.urls import path

from logistics.views import (
    ChooseRateView,
    CreateLabelView,
    MarkDeliveredView,
    MarkShippedView,
    RateQuoteView,
    TrackingWebhookView,
)

urlpatterns = [
    path("shipments/<uuid:pk>/rates/", RateQuoteView.as_view(), name="logistics-rates"),
    path("shipments/<uuid:pk>/choose-rate/", ChooseRateView.as_view(), name="logistics-choose-rate"),
    path("shipments/<uuid:pk>/label/", CreateLabelView.as_view(), name="logistics-label"),
    path("tracking/webhook/", TrackingWebhookView.as_view(), name="logistics-tracking-webhook"),
    path(
        "supplier-orders/<uuid:pk>/mark-shipped/",
        MarkShippedView.as_view(),
        name="logistics-mark-shipped",
    ),
    path(
        "supplier-orders/<uuid:pk>/buyer-confirm-delivery/",
        MarkDeliveredView.as_view(),
        name="logistics-buyer-confirm-delivery",
    ),
]
