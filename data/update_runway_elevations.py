# aviation/management/commands/update_runway_elevations.py

import requests
from django.core.management.base import BaseCommand
from aviation.models import Runway


def get_elevation(lat, lon):
    url = f"https://api.opentopodata.org/v1/srtm90m?locations={lat},{lon}"
    r = requests.get(url, timeout=10).json()
    return r["results"][0]["elevation"]


class Command(BaseCommand):
    help = "Populate runway threshold elevations from DEM"

    def handle(self, *args, **kwargs):

        #for runway in Runway.objects.all():
        for runway in Runway.objects.filter(le_elevation_ft__isnull=True):

            if runway.le_latitude_deg and runway.le_longitude_deg:
                le = get_elevation(runway.le_latitude_deg, runway.le_longitude_deg)
                runway.le_elevation_ft = round(le * 3.28084)

            if runway.he_latitude_deg and runway.he_longitude_deg:
                he = get_elevation(runway.he_latitude_deg, runway.he_longitude_deg)
                runway.he_elevation_ft = round(he * 3.28084)

            runway.save()

            print(
                f"{runway.airport_ident} {runway.le_ident}/{runway.he_ident} "
                f"LE:{runway.le_elevation_ft}ft HE:{runway.he_elevation_ft}ft"
            )