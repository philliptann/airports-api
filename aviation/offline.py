import hashlib
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
import math

from django.http import FileResponse, HttpResponseBadRequest
from django.views.decorators.http import require_GET

from .models import Airport, Runway

def _initial_bearing_deg(lat1, lon1, lat2, lon2):
    """
    Returns initial bearing (true) in degrees from point 1 -> point 2.
    None if inputs missing.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None

    # Convert to radians
    φ1 = math.radians(lat1)
    φ2 = math.radians(lat2)
    Δλ = math.radians(lon2 - lon1)

    y = math.sin(Δλ) * math.cos(φ2)
    x = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(Δλ)

    θ = math.atan2(y, x)  # radians
    bearing = (math.degrees(θ) + 360.0) % 360.0
    return bearing

def _parse_iso_list(param: str) -> list[str]:
    iso_list = [c.strip().upper() for c in (param or "").split(",") if c.strip()]
    # ISO-3166 alpha-2 sanity: 2 letters
    for c in iso_list:
        if len(c) != 2 or not c.isalpha():
            raise ValueError(f"Invalid iso_country value: {c!r}")
    return iso_list


def _dataset_key(iso_list: list[str]) -> str:
    # Stable cache key based on country list (sorted)
    s = ",".join(sorted(iso_list))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


@require_GET
def offline_sqlite(request):
    """
    Download a country-filtered SQLite DB containing airports + runways + thresholds.
    Example:
      /api/offline/sqlite/?iso_country=GB
      /api/offline/sqlite/?iso_country=GB,IE
    """
    iso_param = request.GET.get("iso_country", "GB")
    try:
        iso_list = _parse_iso_list(iso_param)
    except ValueError as e:
        return HttpResponseBadRequest(str(e))

    # Pull airports
    airports_qs = Airport.objects.filter(iso_country__in=iso_list).only(
        "ident", "name", "type", "latitude_deg", "longitude_deg", "elevation_ft",
        "municipality", "iso_region", "iata_code", "iso_country"
    )

    # Materialise airports (we need idents)
    airports = list(airports_qs)
    airport_idents = [a.ident for a in airports if a.ident]

    # Pull runways for those airports (threshold coords are on the runway rows)
    runways_qs = Runway.objects.filter(airport_ident__in=airport_idents).only(
        "airport_ident", "our_id",
        "length_ft", "width_ft", "surface", "lighted", "closed",
        "le_ident", "le_latitude_deg", "le_longitude_deg",
        "he_ident", "he_latitude_deg", "he_longitude_deg",
    )
    runways = list(runways_qs)

    # Build SQLite in a temp file
    tmp = tempfile.NamedTemporaryFile(prefix="ourairports_", suffix=".sqlite", delete=False)
    tmp.close()

    conn = sqlite3.connect(tmp.name)
    try:
        cur = conn.cursor()

        # Pragmas for fast creation
        cur.execute("PRAGMA journal_mode=OFF;")
        cur.execute("PRAGMA synchronous=OFF;")
        cur.execute("PRAGMA temp_store=MEMORY;")

        cur.execute("""
            CREATE TABLE airports (
                ident TEXT PRIMARY KEY,
                name TEXT,
                type TEXT,
                iso_country TEXT,
                iso_region TEXT,
                municipality TEXT,
                iata_code TEXT,
                lat REAL,
                lon REAL,
                elevation_ft INTEGER
            )
        """)

        cur.execute("""
            CREATE TABLE runways (
                runway_our_id INTEGER,
                airport_ident TEXT,
                length_ft INTEGER,
                width_ft INTEGER,
                surface TEXT,
                lighted INTEGER,
                closed INTEGER,
                le_ident TEXT,
                le_lat REAL,
                le_lon REAL,
                he_ident TEXT,
                he_lat REAL,
                he_lon REAL,
                bearing_le_to_he_deg REAL,
                bearing_he_to_le_deg REAL
            )
        """)

        # Bulk insert airports
        cur.executemany(
            "INSERT INTO airports VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    a.ident,
                    a.name or "",
                    a.type or "",
                    a.iso_country or "",
                    a.iso_region or "",
                    a.municipality or "",
                    a.iata_code or "",
                    a.latitude_deg,
                    a.longitude_deg,
                    a.elevation_ft,
                )
                for a in airports
            ],
        )

        # Bulk insert runways
        cur.executemany(
            "INSERT INTO runways VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    r.our_id,
                    r.airport_ident,
                    r.length_ft,
                    r.width_ft,
                    r.surface or "",
                    1 if r.lighted else 0,
                    1 if r.closed else 0,
                    r.le_ident or "",
                    r.le_latitude_deg,
                    r.le_longitude_deg,
                    r.he_ident or "",
                    r.he_latitude_deg,
                    r.he_longitude_deg,
                    _initial_bearing_deg(r.le_latitude_deg, r.le_longitude_deg, r.he_latitude_deg, r.he_longitude_deg),
                    _initial_bearing_deg(r.he_latitude_deg, r.he_longitude_deg, r.le_latitude_deg, r.le_longitude_deg),
                )
                for r in runways
            ],
        )

        # Indexes for fast lookups on device
        cur.execute("CREATE INDEX idx_airports_name ON airports(name);")
        cur.execute("CREATE INDEX idx_runways_airport_ident ON runways(airport_ident);")
        cur.execute("CREATE INDEX idx_runways_le_ident ON runways(le_ident);")
        cur.execute("CREATE INDEX idx_runways_he_ident ON runways(he_ident);")

        # Optional: a metadata table so the app can display version info
        cur.execute("""
            CREATE TABLE meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        generated_at = datetime.now(timezone.utc).isoformat()
        cur.executemany(
            "INSERT INTO meta VALUES (?,?)",
            [
                ("generated_at", generated_at),
                ("iso_country", ",".join(sorted(iso_list))),
                ("airport_count", str(len(airports))),
                ("runway_count", str(len(runways))),
            ],
        )

        conn.commit()
    finally:
        conn.close()

    # Stream file response
    filename = f"ourairports_{'_'.join(sorted(iso_list))}.sqlite"
    resp = FileResponse(open(tmp.name, "rb"), as_attachment=True, filename=filename)

    # Good hygiene: ensure temp file removed after response closes
    # (FileResponse uses a file handle; we can unlink the path after opening on Linux)
    try:
        os.unlink(tmp.name)
    except OSError:
        pass

    return resp
