from rest_framework import serializers
from .models import Airport, Runway

class RunwaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Runway
        fields = "__all__"

class AirportSerializer(serializers.ModelSerializer):
    runways = RunwaySerializer(many=True, read_only=True)

    class Meta:
        model = Airport
        fields = "__all__"

class ThresholdSerializer(serializers.Serializer):
    airport_ident = serializers.CharField()
    runway_our_id = serializers.IntegerField()
    le_ident = serializers.CharField(allow_blank=True)
    le_latitude_deg = serializers.FloatField(allow_null=True)
    le_longitude_deg = serializers.FloatField(allow_null=True)
    he_ident = serializers.CharField(allow_blank=True)
    he_latitude_deg = serializers.FloatField(allow_null=True)
    he_longitude_deg = serializers.FloatField(allow_null=True)
