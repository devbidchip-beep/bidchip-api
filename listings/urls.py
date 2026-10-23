from django.urls import path

from .views import (
    ListingDetailView,
    ListingListCreateView,
    ListingPublishView,
    PublicListingListView,
)

urlpatterns = [
    path("", ListingListCreateView.as_view()),
    path("<uuid:pk>/", ListingDetailView.as_view()),
    path("<uuid:pk>/publish/", ListingPublishView.as_view()),
    path("published/", PublicListingListView.as_view()),
]
