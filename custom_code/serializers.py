from rest_framework import serializers
from custom_code.models import RGESAlert, Event
from tom_targets.models import Target
from tom_dataproducts.models import try_parse_reduced_datum, PhotometryReducedDatum
from astropy.coordinates import SkyCoord
from astropy import units as u
from astropy.time import Time
from django.utils import timezone
import datetime
import numpy as np
from custom_code import utils


class LightCurveBandSerializer(serializers.Serializer):
    """One passband's raw time series, as provided in an MSOS alert packet."""
    time = serializers.ListField(child=serializers.FloatField())
    flux = serializers.ListField(child=serializers.FloatField())
    flux_err = serializers.ListField(child=serializers.FloatField())


class LightCurvesSerializer(serializers.Serializer):
    F087 = LightCurveBandSerializer()
    F146 = LightCurveBandSerializer()
    F213 = LightCurveBandSerializer()


class MSOSMetadataSerializer(serializers.Serializer):
    """
    Serialize selected fields from the MSOS simulated data
    """
    t0lens1 = serializers.FloatField()
    u0lens1 = serializers.FloatField()
    tE_ref = serializers.FloatField()
    rho = serializers.FloatField()
    Source_F146 = serializers.FloatField()
    EventID = serializers.FloatField()


class MSOSAlertSerializer(serializers.Serializer):
    """
    Serializer for a raw MSOS alert packet (JSON), converting it into
    RGESAlert, Target and Event records.
    """
    id = serializers.CharField()
    objname = serializers.CharField()
    ra = serializers.FloatField()
    dec = serializers.FloatField()
    metadata = MSOSMetadataSerializer()
    light_curves = LightCurvesSerializer()

    def create(self, validated_data):

        s = SkyCoord(validated_data['ra'], validated_data['dec'], frame='icrs', unit=(u.deg, u.deg))
        g = s.transform_to('galactic')

        t, created = Target.objects.get_or_create(
            name=validated_data['objname'],
            defaults=dict(
                ra=validated_data['ra'],
                dec=validated_data['dec'],
                type='SIDEREAL',
                permissions='PUBLIC',
                galactic_lng=g.l.deg,
                galactic_lat=g.b.deg,
                t0=float(validated_data['metadata']['t0lens1']),
                u0=float(validated_data['metadata']['u0lens1']),
                tE=float(validated_data['metadata']['tE_ref']),
                source_magnitude=float(validated_data['metadata']['Source_F146']),
                baseline_magnitude=float(validated_data['metadata']['Source_F146']),
            ),
        )

        current_time = timezone.now()

        alert_data = {key: value for key, value in self.initial_data.items() if 'light_curve' not in key}

        duration = 2.0*float(validated_data['metadata']['tE_ref'])
        tstart = float(validated_data['metadata']['t0lens1']) - duration
        event_id = str(int(validated_data['metadata']['EventID']))

        event, created = Event.objects.get_or_create(
            event_id=event_id,
            defaults=dict(
                target=t,
                start_time=tstart,
                duration=duration,
            ),
        )

        alert, created = RGESAlert.objects.get_or_create(
            alert_id=event_id,
            defaults=dict(
                roman_id=validated_data['objname'],
                event=event,
                ra=s.ra.deg,
                dec=s.dec.deg,
                alert_neural_network_confidence=0.0,
                alert_delta_chi2=0.0,
                alert_classification='Microlensing',
                ffp_candidate=True,
                alert_origin='MSOS',    # Classifier name needed in alert packet
                alert_notes='',
                alert_t0=float(validated_data['metadata']['t0lens1']),
                alert_u0=float(validated_data['metadata']['u0lens1']),
                alert_tE=float(validated_data['metadata']['tE_ref']),  # Is this the right value?
                alert_rho=float(validated_data['metadata']['rho']),
                alert_peak_mag=0.0,
                alert_baseline_mag=float(validated_data['metadata']['Source_F146']),  # What about the other passbands?
                alert_mag_passband='F146',
                alert_timestamp=current_time, # Because there is no timestamp in the alert packet
                alert_contents=alert_data,
            ),
        )

        # Parse the lightcurve data into PhotometryReducedDatums
        lightcurves = self.convert_lightcurve_to_mag(validated_data)

        for passband in ['F087', 'F146', 'F213']:
            lc = lightcurves[passband]
            source_name = 'Roman_' + passband  # Replace with classifier ID

            # Bulk create due to large number of datapoints
            reduced_datums = [
                try_parse_reduced_datum({
                    'target': t,
                    'data_product': None,          # No actual file path available
                    'data_type': 'photometry',
                    'source_name': source_name,
                    'source_location': 'Roman',      # Check this
                    'timestamp': timezone.make_aware(Time(lc[i, 0], format='jd').datetime, datetime.timezone.utc),
                    'value': {
                        'mag': lc[i, 1],
                        'mag_err': lc[i, 2],
                        'bandpass': passband
                    }
                })
                for i in range(len(lc))
            ]
            # ignore_conflicts: without it, rerunning ingestion on a file
            # already ingested hits the unique_photometry constraint and
            # raises IntegrityError, aborting the whole batch instead of
            # just skipping the points that already exist.
            PhotometryReducedDatum.objects.bulk_create(reduced_datums, ignore_conflicts=True)

        return alert

    def convert_lightcurve_to_mag(self, validated_data):
        """
        The lightcurve data that comes with an alert packet is a dictionary with keys
        'time', 'flux' and 'flux_err'
        This function converts this to a list of tuples in magnitudes.
        """

        lightcurves = {}
        for passband in ['F087', 'F146', 'F213']:
            mag, mag_err, _, _ = utils.flux_to_mag(
                np.array(validated_data['light_curves'][passband]['flux']),
                np.array(validated_data['light_curves'][passband]['flux_err'])
            )
            lc = [
                [validated_data['light_curves'][passband]['time'][i], mag[i], mag_err[i]]
                for i in range(0, len(validated_data['light_curves'][passband]['time']), 1)
                ]
            lightcurves[passband] = np.array(lc)

        return lightcurves
