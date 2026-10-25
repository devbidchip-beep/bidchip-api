from django.urls import path

from .views import IntakeDetailView, IntakeListView, IntakeUploadView

urlpatterns = [
    path("", IntakeListView.as_view()),
    path("upload/", IntakeUploadView.as_view()),
    path("<uuid:pk>/", IntakeDetailView.as_view()),
]
