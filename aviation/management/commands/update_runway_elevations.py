# aviation/management/commands/update_runway_elevations.py

import time
import requests

from django.core.management.base import BaseCommand
from django.db.models import Q, Subquery

from aviation.models import Runway, Airport

M_TO_FT = 3.28084
BATCH_SIZE = 100


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def fetch_batch(dataset, points):
    locations = "|".join(f"{lat},{lon}" for lat, lon in points)
    url = f"https://api.opentopodata.org/v1/{dataset}?locations={locations}"

    for attempt in range(5):
        r = requests.get(url, timeout=30)

        if r.status_code == 429:
            time.sleep(2 ** attempt)
            continue

        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        return [item.get("elevation") for item in results]

    return [None] * len(points)


class Command(BaseCommand):
    help = "Populate UK runway threshold elevations in batches, with airport fallback"

    def handle(self, *args, **kwargs):
        uk_airports_qs = Airport.objects.filter(iso_country="GB")
        uk_airports = uk_airports_qs.values("ident")

        airport_lookup = {
            a.ident: a
            for a in uk_airports_qs.only("ident", "latitude_deg", "longitude_deg")
        }

        qs = (
            Runway.objects
            .filter(airport_ident__in=Subquery(uk_airports))
            .filter(Q(le_elevation_ft__isnull=True) | Q(he_elevation_ft__isnull=True))
            .order_by("id")
        )

        runways = list(qs)
        self.stdout.write(f"Processing {len(runways)} UK runways")

        # LE
        le_targets = []
        le_points = []

        for r in runways:
            if r.le_elevation_ft is not None:
                continue

            airport = airport_lookup.get(r.airport_ident)
            lat = r.le_latitude_deg if r.le_latitude_deg is not None else getattr(airport, "latitude_deg", None)
            lon = r.le_longitude_deg if r.le_longitude_deg is not None else getattr(airport, "longitude_deg", None)

            if lat is not None and lon is not None:
                le_targets.append(r)
                le_points.append((lat, lon))

        self.stdout.write(f"Updating LE elevations for {len(le_targets)} runway ends")

        for batch_num, idxs in enumerate(range(0, len(le_targets), BATCH_SIZE), start=1):
            batch_targets = le_targets[idxs:idxs + BATCH_SIZE]
            batch_points = le_points[idxs:idxs + BATCH_SIZE]

            elevations = fetch_batch("eudem25m", batch_points)
            missing_idx = [i for i, elev in enumerate(elevations) if elev is None]

            if missing_idx:
                fallback_points = [batch_points[i] for i in missing_idx]
                fallback_elevs = fetch_batch("srtm90m", fallback_points)
                for j, idx in enumerate(missing_idx):
                    elevations[idx] = fallback_elevs[j]

            updated = 0
            for runway, elev in zip(batch_targets, elevations):
                if elev is not None:
                    runway.le_elevation_ft = round(elev * M_TO_FT)
                    updated += 1

            Runway.objects.bulk_update(batch_targets, ["le_elevation_ft"])
            self.stdout.write(f"LE batch {batch_num}: updated {updated}/{len(batch_targets)}")
            time.sleep(1.1)

        # HE
        he_targets = []
        he_points = []

        for r in runways:
            if r.he_elevation_ft is not None:
                continue

            airport = airport_lookup.get(r.airport_ident)
            lat = r.he_latitude_deg if r.he_latitude_deg is not None else getattr(airport, "latitude_deg", None)
            lon = r.he_longitude_deg if r.he_longitude_deg is not None else getattr(airport, "longitude_deg", None)

            if lat is not None and lon is not None:
                he_targets.append(r)
                he_points.append((lat, lon))

        self.stdout.write(f"Updating HE elevations for {len(he_targets)} runway ends")

        for batch_num, idxs in enumerate(range(0, len(he_targets), BATCH_SIZE), start=1):
            batch_targets = he_targets[idxs:idxs + BATCH_SIZE]
            batch_points = he_points[idxs:idxs + BATCH_SIZE]

            elevations = fetch_batch("eudem25m", batch_points)
            missing_idx = [i for i, elev in enumerate(elevations) if elev is None]

            if missing_idx:
                fallback_points = [batch_points[i] for i in missing_idx]
                fallback_elevs = fetch_batch("srtm90m", fallback_points)
                for j, idx in enumerate(missing_idx):
                    elevations[idx] = fallback_elevs[j]

            updated = 0
            for runway, elev in zip(batch_targets, elevations):
                if elev is not None:
                    runway.he_elevation_ft = round(elev * M_TO_FT)
                    updated += 1

            Runway.objects.bulk_update(batch_targets, ["he_elevation_ft"])
            self.stdout.write(f"HE batch {batch_num}: updated {updated}/{len(batch_targets)}")
            time.sleep(1.1)

        self.stdout.write(self.style.SUCCESS("Done"))