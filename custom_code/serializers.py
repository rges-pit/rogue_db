from rest_framework.serializers import ModelSerializer
from custom_code.models import RGESAlert
from tom_targets.models import Target
from astropy.coordinates import SkyCoord
from astropy import units as u
from custom_code import validators

class RGESAlertSerializer(ModelSerializer):
    """
    Serializer to convert alerts in JSON format to RGESAlert objects and Targets.
    """

    class Meta:
        model = RGESAlert
        fields = '__all__'
        validators = []

    def create(self, validated_data):

        s = SkyCoord(validated_data['ra'], validated_data['dec'], frame='icrs', unit=(u.deg, u.deg))
        s.transform_to('galactic')

        t = Target.objects.create(
            name=validated_data['objname'],
            ra=validated_data['ra'],
            dec=validated_data['dec'],
            type='SIDEREAL',
            permissions='PUBLIC',
            galactic_lng=s.l.deg,
            galactic_lat=s.b.deg,
        )

        alert = RGESAlert.objects.create(
            alert_id=validated_data['id'],
            roman_id=validated_data['objname'],
            ra=validated_data['ra'],
            dec=validated_data['dec'],
            alert_t0=validated_data['t0lens1'],
            alert_u0=validated_data['u0lens1'],
            
        )