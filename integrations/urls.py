from django.urls import path

from integrations.views import NimbleQuoteResponseView, NimbleRFQCreateView

urlpatterns = [
    path("nimble/rfqs/", NimbleRFQCreateView.as_view()),
    path("nimble/rfqs/responses/", NimbleQuoteResponseView.as_view()),
]
