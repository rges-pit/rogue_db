from rest_framework.serializers import ModelSerializer
from custom_code.models import RGESAlert
from custom_code.utils import flux_to_mag, mag_to_flux
from tom_targets.models import Target
from tom_dataproducts.serializers import ReducedDatumSerializer
from astropy.coordinates import SkyCoord
from astropy import units as u
from astropy.time import Time
import numpy as np
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

        ## NEEDS REAL ALERT KEYWORD
        if 'confidence' in validated_data.keys():
            alert_confidence = validated_data['confidence']
        else:
            alert_confidence = None
        ## NEEDS REAL ALERT KEYWORD
        if 'delta_chisq' in validated_data.keys():
            delta_chisq = validated_data['delta_chisq']
        else:
            delta_chisq = None

        current_time = Time.now()

        alert_data = {key:value for key, value in validated_data.items() if 'light_curve' not in key}

        alert = RGESAlert.objects.create(
            alert_id=validated_data['id'],
            roman_id=validated_data['objname'],
            target=t,
            ra=validated_data['ra'],
            dec=validated_data['dec'],
            alert_neural_network_confidence=alert_confidence,
            alert_delta_chi2=delta_chisq,
            alert_classification='Microlensing',
            ffp_candidate=True,
            alert_origin='RGES',    # Classifier name needed in alert packet
            alert_notes='',
            alert_t0=validated_data['t0lens1'],
            alert_u0=validated_data['u0lens1'],
            alert_tE=validated_data['tE_ref'],  # Is this the right value?
            alert_rho=validated_data['rho'],
            alert_peak_mag=0.0,
            alert_baseline_mag=validated_data['Source_F213'],  # What about the other passbands?
            alert_mag_passband='F213',
            alert_timestamp=current_time, # Because there is no timestamp in the alert packet
            alert_contents=alert_data,
        )

        # Parse the lightcurve data into PhotometryReducedDatums
        lightcurves = self.convert_lightcurve_to_mag(validated_data)

        for passband in ['F087', 'F146', 'F213']:
            lc = lightcurves[passband]
            payload = [{
                'target': t.pk,
                'data_product': None,          # No actual file path available
                'data_type': 'photometry',
                'source_name': 'MSOS_alert_'+validated_data['id'],  # Replace with classifier ID
                'source_location': 'Roman',      # Check this
                'timestamp': lc[0,i],
                'value': {
                    'mag': lc[1,i],
                    'mag_err': lc[2,i],
                    'bandpass': passband
                }
            } for i in range(0, len(lc), 1)]

            serializer = ReducedDatumSerializer(data=payload, many=True, context=self.get_serializer_context()})
            serializer.is_valid(raise_exception=True)
            rds = serializer.save()

        return alert

    def convert_lightcurve_to_mag(self, validated_data):
        """
        The lightcurve data that comes with an alert packet is a dictionary with keys
        'time', 'flux' and 'flux_err'
        This function converts this to a list of tuples in magnitudes.
        """

        lightcurves = {}
        for passband in ['F087', 'F146', 'F213']:
            mag, mag_err = utils.flux_to_mag(
                validated_data['light_curves'][passband]['flux'],
                validated_data['light_curves'][passband]['flux_err']
            )
            lc = [
                [validated_data['light_curves'][passband]['time'][i], mag[i], mag_err[i]]
                for i in range(0, len(validated_data['light_curves'][passband]['time']), 1)
                ]
            lightcurves[passband] = np.array(lc)

        return lightcurves