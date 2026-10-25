from django.urls import path

from .views import (
    InventoryBulkUploadView,
    InventoryItemDetailView,
    InventoryItemListCreateView,
    ManufacturerListView,
    PartDetailView,
    PartSearchView,
)

urlpatterns = [
    path("parts/search/", PartSearchView.as_view()),
    path("parts/<int:pk>/", PartDetailView.as_view()),
    path("manufacturers/", ManufacturerListView.as_view()),
    # Inventory — order matters: upload/ must come before <uuid:pk>/
    path("inventory/upload/", InventoryBulkUploadView.as_view()),
    path("inventory/", InventoryItemListCreateView.as_view()),
    path("inventory/<uuid:pk>/", InventoryItemDetailView.as_view()),
]
