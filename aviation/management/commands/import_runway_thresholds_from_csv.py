# aviation/management/commands/import_runway_thresholds_from_csv.py

import csv
import re
from pathlib import Path

from django.core.management.base import BaseCommand
from aviation.models import Runway


def clean(v):
    if v is None:
        return None
    v = str(v).strip()
    return v if v != "" else None


def clean_float(v):
    v = clean(v)
    return float(v) if v is not None else None


def clean_int(v):
    v = clean(v)
    return int(float(v)) if v is not None else None


def norm_ident(value):
    """
    Normalise standard runway idents:
      7   -> 07
      8   -> 08
      1L  -> 01L
      9R  -> 09R

    Leave non-standard values unchanged:
      H1, N/S, E/W, NW, SE, ., ..
    """
    value = clean(value)
    if value is None:
        return None

    v = value.upper()

    m = re.fullmatch(r"(\d{1,2})([LRC]?)", v)
    if m:
        num = int(m.group(1))
        suffix = m.group(2)
        return f"{num:02d}{suffix}"

    return v


class Command(BaseCommand):
    help = "Import missing runway threshold coords/elevations from CSV"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--report-file",
            type=str,
            default="runway_thresholds_not_found_report.csv",
            help="CSV file to write unmatched rows to",
        )

    def handle(self, *args, **options):
        csv_file = Path(options["csv_file"])
        dry_run = options["dry_run"]
        report_file = Path(options["report_file"])

        updated_rows = 0
        not_found = 0
        reversed_matches = 0
        unchanged_rows = 0
        not_found_rows = []

        with csv_file.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for row in reader:
                airport_ident = clean(row.get("airport_ident"))
                csv_le_ident_raw = clean(row.get("le_ident"))
                csv_he_ident_raw = clean(row.get("he_ident"))

                csv_le_ident = norm_ident(csv_le_ident_raw)
                csv_he_ident = norm_ident(csv_he_ident_raw)

                if not airport_ident or not csv_le_ident:
                    continue

                csv_le_lat = clean_float(row.get("le_latitude_deg"))
                csv_le_lon = clean_float(row.get("le_longitude_deg"))
                csv_le_elev = clean_int(row.get("le_elevation_ft"))

                csv_he_lat = clean_float(row.get("he_latitude_deg"))
                csv_he_lon = clean_float(row.get("he_longitude_deg"))
                csv_he_elev = clean_int(row.get("he_elevation_ft"))

                candidates = list(Runway.objects.filter(airport_ident=airport_ident))

                runway = None
                matched_reversed = False

                for candidate in candidates:
                    db_le_ident = norm_ident(candidate.le_ident)
                    db_he_ident = norm_ident(candidate.he_ident)

                    if db_le_ident == csv_le_ident and db_he_ident == csv_he_ident:
                        runway = candidate
                        matched_reversed = False
                        break

                    if db_le_ident == csv_he_ident and db_he_ident == csv_le_ident:
                        runway = candidate
                        matched_reversed = True
                        break

                if not runway:
                    not_found += 1

                    candidate_pairs = "; ".join(
                        f"{c.le_ident}/{c.he_ident}" for c in candidates
                    ) if candidates else ""

                    not_found_rows.append({
                        "airport_ident": airport_ident,
                        "csv_le_ident": csv_le_ident_raw,
                        "csv_he_ident": csv_he_ident_raw,
                        "norm_le_ident": csv_le_ident,
                        "norm_he_ident": csv_he_ident,
                        "reason": "no matching runway for airport" if candidates else "airport not found in runway table",
                        "db_candidate_pairs": candidate_pairs,
                        "csv_le_latitude_deg": row.get("le_latitude_deg"),
                        "csv_le_longitude_deg": row.get("le_longitude_deg"),
                        "csv_he_latitude_deg": row.get("he_latitude_deg"),
                        "csv_he_longitude_deg": row.get("he_longitude_deg"),
                        "csv_le_elevation_ft": row.get("le_elevation_ft"),
                        "csv_he_elevation_ft": row.get("he_elevation_ft"),
                    })

                    self.stdout.write(
                        self.style.WARNING(
                            f"Not found: {airport_ident} "
                            f"{csv_le_ident_raw}/{csv_he_ident_raw} "
                            f"(normalised: {csv_le_ident}/{csv_he_ident})"
                        )
                    )
                    continue

                if matched_reversed:
                    reversed_matches += 1
                    csv_le_lat, csv_he_lat = csv_he_lat, csv_le_lat
                    csv_le_lon, csv_he_lon = csv_he_lon, csv_le_lon
                    csv_le_elev, csv_he_elev = csv_he_elev, csv_le_elev

                changed = False

                if (
                    (runway.le_latitude_deg is None or runway.le_longitude_deg is None)
                    and csv_le_lat is not None
                    and csv_le_lon is not None
                ):
                    if csv_le_elev is not None:
                        runway.le_elevation_ft = csv_le_elev
                    runway.le_latitude_deg = csv_le_lat
                    runway.le_longitude_deg = csv_le_lon
                    changed = True

                if (
                    (runway.he_latitude_deg is None or runway.he_longitude_deg is None)
                    and csv_he_lat is not None
                    and csv_he_lon is not None
                ):
                    if csv_he_elev is not None:
                        runway.he_elevation_ft = csv_he_elev
                    runway.he_latitude_deg = csv_he_lat
                    runway.he_longitude_deg = csv_he_lon
                    changed = True

                if changed:
                    updated_rows += 1
                    match_note = " [reversed]" if matched_reversed else ""
                    self.stdout.write(
                        f"Update: {runway.airport_ident} "
                        f"{runway.le_ident}/{runway.he_ident}{match_note}"
                    )
                    if not dry_run:
                        runway.save()
                else:
                    unchanged_rows += 1

        if not_found_rows:
            report_file.parent.mkdir(parents=True, exist_ok=True)
            with report_file.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "airport_ident",
                        "csv_le_ident",
                        "csv_he_ident",
                        "norm_le_ident",
                        "norm_he_ident",
                        "reason",
                        "db_candidate_pairs",
                        "csv_le_latitude_deg",
                        "csv_le_longitude_deg",
                        "csv_he_latitude_deg",
                        "csv_he_longitude_deg",
                        "csv_le_elevation_ft",
                        "csv_he_elevation_ft",
                    ],
                )
                writer.writeheader()
                writer.writerows(not_found_rows)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Updated {updated_rows} runways. "
                f"Reversed matches: {reversed_matches}. "
                f"Unchanged: {unchanged_rows}. "
                f"Not found: {not_found}. "
                f"Dry run: {dry_run}. "
                f"Report: {report_file}"
            )
        )