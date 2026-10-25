"""
Trust URL configuration.
"""

from django.urls import path

from trust.views import (
    DisputeDetailView,
    DisputeListCreateView,
    MessageThreadDetailView,
    MessageThreadListCreateView,
    ModerateMessageView,
    RatingListCreateView,
    RiskAssessmentView,
    SendMessageView,
)

urlpatterns = [
    path("disputes/", DisputeListCreateView.as_view()),
    path("disputes/<uuid:pk>/", DisputeDetailView.as_view()),
    path("ratings/", RatingListCreateView.as_view()),
    path("threads/", MessageThreadListCreateView.as_view()),
    path("threads/<uuid:pk>/", MessageThreadDetailView.as_view()),
    path("threads/<uuid:pk>/messages/", SendMessageView.as_view()),
    path("messages/<uuid:pk>/moderate/", ModerateMessageView.as_view()),
    path("risk/<uuid:supplier_order_id>/", RiskAssessmentView.as_view()),
]
