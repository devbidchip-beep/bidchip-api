from django.urls import path

from .views import ManufacturerListView, PartDetailView, PartSearchView

urlpatterns = [
    path("parts/search/", PartSearchView.as_view()),
    path("parts/<int:pk>/", PartDetailView.as_view()),
    path("manufacturers/", ManufacturerListView.as_view()),
]
