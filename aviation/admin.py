#backup-aws/airports-api/aviation/admin.py
from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import Airport, Runway

class AirportResource(resources.ModelResource):
    class Meta:
        model = Airport
        import_id_fields = ("our_id",)
        fields = (
            "our_id","ident","type","name",
            "latitude_deg","longitude_deg","elevation_ft",
            "iso_country","iso_region","municipality",
            "iata_code","gps_code","local_code",
        )

@admin.register(Airport)
class AirportAdmin(ImportExportModelAdmin):
    resource_class = AirportResource
    search_fields = ("ident","name","iata_code","iso_country","iso_region")
    list_filter = ("iso_country","type")
    list_display = ("ident","name","type","iso_country","iso_region","iata_code")

class RunwayResource(resources.ModelResource):
    class Meta:
        model = Runway
        import_id_fields = ("our_id",)
        fields = (
            "our_id","airport_ident",
            "length_ft","width_ft","surface","lighted","closed",
            "le_ident","le_latitude_deg","le_longitude_deg","le_elevation_ft",
            "he_ident","he_latitude_deg","he_longitude_deg","he_elevation_ft",
        )

@admin.register(Runway)
class RunwayAdmin(ImportExportModelAdmin):
    resource_class = RunwayResource

    search_fields = ("airport_ident", "le_ident", "he_ident", "surface")
    list_filter = ("surface", "closed", "lighted")

    list_display = (
        "airport_ident",
        "le_ident",
        "he_ident",
        "length_ft",
        "surface",
        "lighted",
        "closed",
        "le_elevation_ft",
        "he_elevation_ft",
    )

    ordering = ("airport_ident", "le_ident")
    list_select_related = ("airport",)
    list_per_page = 50

    fieldsets = (
        ("Airport", {
            "fields": ("airport", "airport_ident"),
        }),
        ("Dimensions", {
            "fields": ("length_ft", "width_ft", "surface", "lighted", "closed"),
        }),
        ("Low End (LE)", {
            "fields": (
                "le_ident",
                "le_latitude_deg",
                "le_longitude_deg",
                "le_elevation_ft",
            ),
        }),
        ("High End (HE)", {
            "fields": (
                "he_ident",
                "he_latitude_deg",
                "he_longitude_deg",
                "he_elevation_ft",
            ),
        }),
    )