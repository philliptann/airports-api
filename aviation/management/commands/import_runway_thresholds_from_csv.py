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


def ident_parts(value):
    """
    Returns:
      (num:int|None, suffix:str|None, norm:str|None)
    Examples:
      07L -> (7, 'L', '07L')
      25  -> (25, '', '25')
      H1  -> (None, None, 'H1')
    """
    v = norm_ident(value)
    if v is None:
        return None, None, None

    m = re.fullmatch(r"(\d{2})([LRC]?)", v)
    if m:
        return int(m.group(1)), m.group(2), v

    return None, None, v


def is_standard_runway_ident(value):
    num, _suffix, _norm = ident_parts(value)
    return num is not None


def pair_matches(csv_le, csv_he, db_le, db_he, allow_heading_tolerance=True):
    """
    Returns:
      (matched: bool, reversed_match: bool, mode: str)

    Modes:
      exact               07/25 == 07/25
      reversed            25/07 == 07/25
      base_exact          07/25 == 07L/25R
      base_reversed       25/07 == 07L/25R
      tolerance_exact     07/25 ~= 08/26
      tolerance_reversed  25/07 ~= 08/26
    """
    csv_le_num, _csv_le_suffix, csv_le_norm = ident_parts(csv_le)
    csv_he_num, _csv_he_suffix, csv_he_norm = ident_parts(csv_he)
    db_le_num, _db_le_suffix, db_le_norm = ident_parts(db_le)
    db_he_num, _db_he_suffix, db_he_norm = ident_parts(db_he)

    # 1) Exact normalised match
    if csv_le_norm == db_le_norm and csv_he_norm == db_he_norm:
        return True, False, "exact"

    if csv_le_norm == db_he_norm and csv_he_norm == db_le_norm:
        return True, True, "reversed"

    # From here on, only for standard numeric runway idents
    if None in (csv_le_num, csv_he_num, db_le_num, db_he_num):
        return False, False, ""

    # 2) Base-number match (ignores L/R/C)
    if csv_le_num == db_le_num and csv_he_num == db_he_num:
        return True, False, "base_exact"

    if csv_le_num == db_he_num and csv_he_num == db_le_num:
        return True, True, "base_reversed"

    # 3) ±1 runway tolerance
    if allow_heading_tolerance:
        if abs(csv_le_num - db_le_num) <= 1 and abs(csv_he_num - db_he_num) <= 1:
            return True, False, "tolerance_exact"

        if abs(csv_le_num - db_he_num) <= 1 and abs(csv_he_num - db_le_num) <= 1:
            return True, True, "tolerance_reversed"

    return False, False, ""


class Command(BaseCommand):
    help = "Import missing runway threshold coords/elevations from CSV"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--report-file",
            type=str,
            default="runway_thresholds_not_found_report.csv",
            help="CSV file to write unmatched/ambiguous rows to",
        )

    def handle(self, *args, **options):
        csv_file = Path(options["csv_file"])
        dry_run = options["dry_run"]
        report_file = Path(options["report_file"])

        updated_rows = 0
        unchanged_rows = 0
        not_found = 0
        reversed_matches = 0
        ambiguous_matches = 0

        report_rows = []

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

                if not candidates:
                    not_found += 1
                    report_rows.append({
                        "airport_ident": airport_ident,
                        "csv_le_ident": csv_le_ident_raw,
                        "csv_he_ident": csv_he_ident_raw,
                        "norm_le_ident": csv_le_ident,
                        "norm_he_ident": csv_he_ident,
                        "reason": "airport not found in runway table",
                        "match_mode": "",
                        "db_candidate_pairs": "",
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

                matches = []
                for candidate in candidates:
                    matched, reversed_match, mode = pair_matches(
                        csv_le_ident,
                        csv_he_ident,
                        candidate.le_ident,
                        candidate.he_ident,
                        allow_heading_tolerance=True,
                    )
                    if matched:
                        matches.append((candidate, reversed_match, mode))

                # No matches at all
                if not matches:
                    not_found += 1
                    candidate_pairs = "; ".join(
                        f"{c.le_ident}/{c.he_ident}" for c in candidates
                    )
                    report_rows.append({
                        "airport_ident": airport_ident,
                        "csv_le_ident": csv_le_ident_raw,
                        "csv_he_ident": csv_he_ident_raw,
                        "norm_le_ident": csv_le_ident,
                        "norm_he_ident": csv_he_ident,
                        "reason": "no matching runway for airport",
                        "match_mode": "",
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

                # Prefer stronger match modes first
                mode_rank = {
                    "exact": 0,
                    "reversed": 1,
                    "base_exact": 2,
                    "base_reversed": 3,
                    "tolerance_exact": 4,
                    "tolerance_reversed": 5,
                }
                matches.sort(key=lambda item: mode_rank[item[2]])
                best_rank = mode_rank[matches[0][2]]
                best_matches = [m for m in matches if mode_rank[m[2]] == best_rank]

                # Ambiguous best match => do not auto-update
                if len(best_matches) > 1:
                    ambiguous_matches += 1
                    candidate_pairs = "; ".join(
                        f"{m[0].le_ident}/{m[0].he_ident} [{m[2]}]" for m in best_matches
                    )
                    report_rows.append({
                        "airport_ident": airport_ident,
                        "csv_le_ident": csv_le_ident_raw,
                        "csv_he_ident": csv_he_ident_raw,
                        "norm_le_ident": csv_le_ident,
                        "norm_he_ident": csv_he_ident,
                        "reason": "ambiguous runway match",
                        "match_mode": best_matches[0][2],
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
                            f"Ambiguous: {airport_ident} "
                            f"{csv_le_ident_raw}/{csv_he_ident_raw} -> {candidate_pairs}"
                        )
                    )
                    continue

                runway, matched_reversed, match_mode = best_matches[0]

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
                    note = f" [{match_mode}]"
                    if matched_reversed:
                        note += " [reversed]"
                    self.stdout.write(
                        f"Update: {runway.airport_ident} {runway.le_ident}/{runway.he_ident}{note}"
                    )
                    if not dry_run:
                        runway.save()
                else:
                    unchanged_rows += 1

        if report_rows:
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
                        "match_mode",
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
                writer.writerows(report_rows)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Updated {updated_rows} runways. "
                f"Reversed matches: {reversed_matches}. "
                f"Ambiguous: {ambiguous_matches}. "
                f"Unchanged: {unchanged_rows}. "
                f"Not found: {not_found}. "
                f"Dry run: {dry_run}. "
                f"Report: {report_file}"
            )
        )