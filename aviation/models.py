#backup-aws/airports-api/aviation/models.py
from django.db import models

class Airport(models.Model):
    # OurAirports airports.csv
    our_id = models.IntegerField(unique=True, db_index=True)  # "id"
    ident = models.CharField(max_length=10, unique=True, db_index=True)  # "ident"
    type = models.CharField(max_length=40, blank=True)
    name = models.CharField(max_length=255, blank=True)

    latitude_deg = models.FloatField(null=True, blank=True)
    longitude_deg = models.FloatField(null=True, blank=True)
    elevation_ft = models.IntegerField(null=True, blank=True)

    iso_country = models.CharField(max_length=2, blank=True, db_index=True)
    iso_region = models.CharField(max_length=10, blank=True, db_index=True)
    municipality = models.CharField(max_length=255, blank=True)

    iata_code = models.CharField(max_length=3, blank=True, db_index=True)
    gps_code = models.CharField(max_length=10, blank=True)
    local_code = models.CharField(max_length=10, blank=True)

    def __str__(self) -> str:
        n = (self.name or "").strip()
        return f"{self.ident} - {n}".strip(" -")


class Runway(models.Model):
    # OurAirports runways.csv
    our_id = models.IntegerField(unique=True, db_index=True)  # "id"
    airport_ident = models.CharField(max_length=10, db_index=True)
    airport = models.ForeignKey(
        Airport,
        to_field="ident",
        db_column="airport_fk_ident", 
        related_name="runways",
        on_delete=models.CASCADE,
    )

    length_ft = models.IntegerField(null=True, blank=True)
    width_ft = models.IntegerField(null=True, blank=True)
    surface = models.CharField(max_length=120, blank=True)
    lighted = models.BooleanField(default=False)
    closed = models.BooleanField(default=False)

    le_ident = models.CharField(max_length=10, blank=True)  # e.g. 09
    le_latitude_deg = models.FloatField(null=True, blank=True)
    le_longitude_deg = models.FloatField(null=True, blank=True)
    le_elevation_ft = models.IntegerField(null=True, blank=True)

    he_ident = models.CharField(max_length=10, blank=True)  # e.g. 27
    he_latitude_deg = models.FloatField(null=True, blank=True)
    he_longitude_deg = models.FloatField(null=True, blank=True)
    he_elevation_ft = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["airport_ident", "le_ident"]),
            models.Index(fields=["airport_ident", "he_ident"]),
        ]

    def __str__(self) -> str:
        return f"{self.airport_ident} RWY {self.le_ident}/{self.he_ident}".strip()
