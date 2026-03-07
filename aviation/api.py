from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from django_filters.rest_framework import FilterSet, filters

from .models import Airport, Runway
from .serializers import AirportSerializer, RunwaySerializer, ThresholdSerializer


class AirportFilter(FilterSet):
    q = filters.CharFilter(method="search")

    def search(self, qs, name, value):
        v = value.strip()
        if not v:
            return qs
        return qs.filter(
            Q(name__icontains=v) |
            Q(ident__icontains=v) |
            Q(iata_code__iexact=v)
        )

    class Meta:
        model = Airport
        fields = ["ident", "iso_country", "iso_region", "type", "iata_code"]


class AirportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Airport.objects.all().order_by("ident")
    serializer_class = AirportSerializer
    filterset_class = AirportFilter
    lookup_field = "ident"

    @action(detail=True, methods=["get"], url_path="thresholds")
    def thresholds(self, request, ident=None):
        runways = Runway.objects.filter(airport_ident=ident).order_by("le_ident", "he_ident")
        data = [
            {
                "airport_ident": r.airport_ident,
                "runway_our_id": r.our_id,
                "le_ident": r.le_ident or "",
                "le_latitude_deg": r.le_latitude_deg,
                "le_longitude_deg": r.le_longitude_deg,
                "he_ident": r.he_ident or "",
                "he_latitude_deg": r.he_latitude_deg,
                "he_longitude_deg": r.he_longitude_deg,
            }
            for r in runways
        ]
        return Response(ThresholdSerializer(data, many=True).data)


class RunwayViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Runway.objects.select_related("airport").all().order_by("airport_ident", "le_ident", "he_ident")
    serializer_class = RunwaySerializer
    filterset_fields = ["airport_ident", "surface", "closed", "lighted"]


class ThresholdViewSet(viewsets.ViewSet):
    """Flat threshold feed (handy for GIS / ingestion)."""

    def list(self, request):
        airport_ident = (request.query_params.get("airport_ident") or "").strip()
        qs = Runway.objects.all()
        if airport_ident:
            qs = qs.filter(airport_ident=airport_ident)

        qs = qs.order_by("airport_ident", "le_ident", "he_ident")

        data = [
            {
                "airport_ident": r.airport_ident,
                "runway_our_id": r.our_id,
                "le_ident": r.le_ident or "",
                "le_latitude_deg": r.le_latitude_deg,
                "le_longitude_deg": r.le_longitude_deg,
                "he_ident": r.he_ident or "",
                "he_latitude_deg": r.he_latitude_deg,
                "he_longitude_deg": r.he_longitude_deg,
            }
            for r in qs
        ]
        return Response(ThresholdSerializer(data, many=True).data)
