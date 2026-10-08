from rest_framework import serializers
from custom_code.models import RGESAlert, Event
from tom_targets.models import Target
from tom_dataproducts.models import try_parse_reduced_datum, PhotometryReducedDatum
from astropy.coordinates import SkyCoord
from astropy import units as u
from astropy.time import Time
from django.utils import timezone
import warnings
from erfa import ErfaWarning
import datetime
import numpy as np
from custom_code import utils
from custom_code.tasks import compute_periodogram
import logging

logger = logging.getLogger(__name__)

def get_event_id(source, alert_id):
    event_id = source.name + '_' + alert_id
    logger.info('Event ID: ' + event_id)
    return event_id

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
                mag_now_passband='Roman_F146'
            ),
        )
        self.target = t

        if created:
            logger.info('Ingested new source ' + t.name)
        else:
            logger.info('Alert for existing source ' + t.name)

        current_time = timezone.now()

        alert_data = {key: value for key, value in self.initial_data.items() if 'light_curve' not in key}

        # Note the t0 values in the MSOS alerts don't seem to represent the event peak
        duration = 4.0*float(validated_data['metadata']['tE_ref'])
        tstart = float(validated_data['metadata']['t0lens1']) - duration/2.0
        event_id = get_event_id(t, validated_data['id'])

        e, created = Event.objects.get_or_create(
            event_id=event_id,
            defaults=dict(
                target=t,
                start_time=tstart,
                duration=duration,
                peak_mag=0.0
            ),
        )
        self.event = e

        if created:
            logger.info('New event ' + e.event_id)
        else:
            logger.info('Existing event ' + e.event_id)

        # An alert is identified by its packet ID, source, origin and event; the rest goes in
        # defaults so that it is used only when the alert is first recorded. Fields that change between runs
        # (the ingest timestamp, and the peak magnitude, which is estimated and stored below)
        # must not be part of the lookup, or a repeat ingest never finds the first and records
        # the alert again.
        alert, created = RGESAlert.objects.get_or_create(
            alert_id=validated_data['id'],
            roman_id=validated_data['objname'],
            event=e,
            alert_origin='MSOS',    # Classifier name needed in alert packet
            defaults=dict(
                target=t,
                ra=s.ra.deg,
                dec=s.dec.deg,
                alert_neural_network_confidence=0.0,
                alert_delta_chi2=0.0,
                alert_classification='Microlensing',
                ffp_candidate=True,
                alert_notes='',
                alert_t0=float(validated_data['metadata']['t0lens1']),
                alert_u0=float(validated_data['metadata']['u0lens1']),
                alert_tE=float(validated_data['metadata']['tE_ref']),  # Is this the right value?
                alert_rho=float(validated_data['metadata']['rho']),
                alert_peak_mag=0.0,
                alert_baseline_mag=float(validated_data['metadata']['Source_F146']),  # What about the other passbands?
                alert_mag_passband='F146',
                alert_timestamp=current_time,  # Because there is no timestamp in the alert packet
                alert_contents=alert_data,
            ),
        )
        self.alert = alert

        if created:
            logger.info(f'Recorded new alert {alert.alert_id}')
        else:
            logger.info(f'Existing alert {alert.alert_id}')

        # Parse the lightcurve data into PhotometryReducedDatums
        lightcurves = self.convert_lightcurve_to_mag(validated_data)

        if len(lightcurves) > 0:

            # If no alert_peak_mag is given, estimate it from the lightcurve in F146
            if alert.alert_peak_mag == 0.0:
                peak_mag = estimate_peak_mag(e, lightcurves['F146'])
                RGESAlert.objects.filter(pk=alert.pk).update(alert_peak_mag=peak_mag)
                Event.objects.filter(pk=e.pk).update(peak_mag=peak_mag)

            # Supress ERFA warnings on conversion of timestamps >5yrs away from the last known
            # leap second; simulated Roman lightcurves exceed this
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=ErfaWarning, message=".*dubious year.*")

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

                    # ignore_conflicts to ingest just the new datapoints and avoid
                    # crashing if any are duplicates
                    PhotometryReducedDatum.objects.bulk_create(reduced_datums, ignore_conflicts=True)

                    logger.info('Ingested timeseries photometry for ' + t.name)

            compute_periodogram.enqueue(t.pk)
            logger.info('Computed periodogram for ' + t.name)

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

        logger.info('Parsed timeseries photometry')

        return lightcurves

def estimate_peak_mag(lcevent, lightcurve):
    """
    Function to estimate an event's peak magnitude if none is given in the alert packet
    """

    idx = np.where(
        (lightcurve[:,0] >= lcevent.start_time)
        & (lightcurve[:,0] <= lcevent.start_time + lcevent.duration))

    return lightcurve[idx,1].max()

