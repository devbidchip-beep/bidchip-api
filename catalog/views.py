from rest_framework import generics, filters
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from .models import Manufacturer, Part
from .serializers import ManufacturerSerializer, PartSearchResultSerializer, PartSerializer
from .utils import normalize_mpn


class PartSearchAnonThrottle(AnonRateThrottle):
    rate = "10/min"


class PartSearchUserThrottle(UserRateThrottle):
    rate = "60/min"


class PartSearchView(generics.ListAPIView):
    """
    GET /api/v1/catalog/parts/search/?q=LM317T&limit=20

    Searches parts using trigram similarity on mpn_normalized.
    Falls back to icontains if q < 3 characters.
    """
    serializer_class = PartSearchResultSerializer
    permission_classes = [AllowAny]
    throttle_classes = [PartSearchAnonThrottle, PartSearchUserThrottle]

    def get_queryset(self):
        q = self.request.query_params.get("q", "").strip()
        limit = int(self.request.query_params.get("limit", 20))
        limit = min(limit, 100)  # cap at 100

        if not q:
            return Part.objects.none()

        q_normalized = normalize_mpn(q)

        if len(q_normalized) < 3:
            qs = Part.objects.filter(
                mpn_normalized__icontains=q_normalized
            ).select_related("manufacturer")
        else:
            qs = Part.objects.filter(
                mpn_normalized__trigram_similar=q_normalized
            ).select_related("manufacturer")

        return qs[:limit]


class PartDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/catalog/parts/{id}/
    """
    queryset = Part.objects.select_related("manufacturer")
    serializer_class = PartSerializer
    permission_classes = [AllowAny]


class ManufacturerListView(generics.ListAPIView):
    """
    GET /api/v1/catalog/manufacturers/?search=texas
    """
    serializer_class = ManufacturerSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "name_normalized"]

    def get_queryset(self):
        qs = Manufacturer.objects.filter(is_active=True)
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(name_normalized__icontains=search.upper())
        return qs
