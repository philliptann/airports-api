#backup-aws/airports-api/aviation/management/commands/import_ourairports.py
import csv
import io
import requests

from django.core.management.base import BaseCommand
from django.db import transaction

from aviation.models import Airport, Runway

# Convenient raw CSV mirror (OurAirports data repo)
AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
RUNWAYS_URL  = "https://davidmegginson.github.io/ourairports-data/runways.csv"

def _to_int(v):
    try:
        return int(v) if v not in (None, "", "\\N") else None
    except ValueError:
        return None

def _to_float(v):
    try:
        return float(v) if v not in (None, "", "\\N") else None
    except ValueError:
        return None

def _to_bool01(v):
    return str(v).strip() in ("1", "true", "True", "yes", "Y")

class Command(BaseCommand):
    help = "Download and import OurAirports airports.csv and runways.csv into Postgres (upsert)"

    def add_arguments(self, parser):
        parser.add_argument("--airports-url", default=AIRPORTS_URL)
        parser.add_argument("--runways-url", default=RUNWAYS_URL)

    @transaction.atomic
    def handle(self, *args, **opts):
        self.stdout.write("Downloading airports.csv ...")
        airports_csv = requests.get(opts["airports_url"], timeout=60)
        airports_csv.raise_for_status()

        self.stdout.write("Importing airports ...")
        reader = csv.DictReader(io.StringIO(airports_csv.text))
        airport_count = 0
        for r in reader:
            our_id = _to_int(r.get("id"))
            ident = (r.get("ident") or "").strip()
            if not our_id or not ident:
                continue

            Airport.objects.update_or_create(
                our_id=our_id,
                defaults={
                    "ident": ident,
                    "type": (r.get("type") or "").strip(),
                    "name": (r.get("name") or "").strip(),
                    "latitude_deg": _to_float(r.get("latitude_deg")),
                    "longitude_deg": _to_float(r.get("longitude_deg")),
                    "elevation_ft": _to_int(r.get("elevation_ft")),
                    "iso_country": (r.get("iso_country") or "").strip(),
                    "iso_region": (r.get("iso_region") or "").strip(),
                    "municipality": (r.get("municipality") or "").strip(),
                    "iata_code": (r.get("iata_code") or "").strip(),
                    "gps_code": (r.get("gps_code") or "").strip(),
                    "local_code": (r.get("local_code") or "").strip(),
                },
            )
            airport_count += 1

        self.stdout.write(f"Airports upserted: {airport_count}")

        self.stdout.write("Downloading runways.csv ...")
        runways_csv = requests.get(opts["runways_url"], timeout=60)
        runways_csv.raise_for_status()

        self.stdout.write("Importing runways ...")
        reader = csv.DictReader(io.StringIO(runways_csv.text))
        runway_count = 0
        missing_airports = 0

        for r in reader:
            our_id = _to_int(r.get("id"))
            ident = (r.get("airport_ident") or "").strip()
            if not our_id or not ident:
                continue

            airport = Airport.objects.filter(ident=ident).first()
            if not airport:
                missing_airports += 1
                continue

            Runway.objects.update_or_create(
                our_id=our_id,
                defaults={
                    "airport": airport,
                    "airport_ident": ident,
                    "length_ft": _to_int(r.get("length_ft")),
                    "width_ft": _to_int(r.get("width_ft")),
                    "surface": (r.get("surface") or "").strip(),
                    "lighted": _to_bool01(r.get("lighted")),
                    "closed": _to_bool01(r.get("closed")),
                    "le_ident": (r.get("le_ident") or "").strip(),
                    "le_latitude_deg": _to_float(r.get("le_latitude_deg")),
                    "le_longitude_deg": _to_float(r.get("le_longitude_deg")),
                    "le_elevation_ft": _to_int(r.get("le_elevation_ft")), 

                    "he_ident": (r.get("he_ident") or "").strip(),
                    "he_latitude_deg": _to_float(r.get("he_latitude_deg")),
                    "he_longitude_deg": _to_float(r.get("he_longitude_deg")),
                    "he_elevation_ft": _to_int(r.get("he_elevation_ft")),
                },
            )
            runway_count += 1

        self.stdout.write(f"Runways upserted: {runway_count}")
        if missing_airports:
            self.stdout.write(f"Runways skipped (missing airport): {missing_airports}")

        self.stdout.write(self.style.SUCCESS("OurAirports import complete ✅"))
