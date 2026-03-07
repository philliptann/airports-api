from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from aviation.api import AirportViewSet, RunwayViewSet, ThresholdViewSet
from aviation.offline import offline_sqlite
from aviation.health import health

router = DefaultRouter()
router.register(r"airports", AirportViewSet, basename="airports")
router.register(r"runways", RunwayViewSet, basename="runways")
router.register(r"thresholds", ThresholdViewSet, basename="thresholds")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/", include(router.urls)),
    path("api/offline/sqlite/", offline_sqlite),
]
