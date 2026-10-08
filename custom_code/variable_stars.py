from custom_code.models import VariableStar, SourceDiagnostics
from custom_code.target_models import RogueTarget
from custom_code import data_utils
from astropy.coordinates import SkyCoord
from astropy import units as u
from astropy.timeseries import LombScargle
import numpy as np
import logging

logger = logging.getLogger(__name__)

def find_nearest_rges_variable_catalog(target, diagnostics, radius=2):
    """
    Function to check whether there is a star nearby to the Target in the VariableStar table.
    This is stored as the variable star name (nearest_variable_star) and angular separation
    (angular_separation_variable)
    Default search radius is 30 arcsec
    Pattern follows the TOM Toolkit's approach to MatchManagers
    """

    radius /= 3600  # Convert radius from arcseconds to degrees
    double_radius = radius * 2

    # Query using a box filter to limit the number of
    qs = VariableStar.objects.filter(
        ra__gte=target.ra - double_radius, ra__lte=target.ra + double_radius,
        dec__gte=target.dec - double_radius, dec__lte=target.dec + double_radius
    )
    logger.info('Checking for nearby variable stars, found ' + str(qs.count()) + ' stars in the vicinity')

    # Calculate the angular separation between the target and the selected VariableStar entries,
    # and identify the closest known variable
    if qs.count() > 0:
        ras = [vstar.ra for vstar in qs]
        decs = [vstar.dec for vstar in qs]

        variables = SkyCoord(ras, decs, frame='icrs', unit=(u.deg, u.deg))
        source = SkyCoord(target.ra, target.dec, frame='icrs', unit=(u.deg, u.deg))
        separation = source.separation(variables)
        closest_idx = int(np.argmin(separation))  # QuerySet indexing rejects numpy's int64
        closest_separation_deg = separation[closest_idx].deg

        # Update diagnostics with information about the nearest variable star, if the nearest
        # star is closer than the search radius
        if closest_separation_deg <= radius:  # In degrees
            vstar = qs[closest_idx]

            if vstar.type == 'flare':
                diagnostics['nearest_flare_star'] = vstar.get_name()
                diagnostics['angular_separation_flare_star'] = closest_separation_deg

            else:
                diagnostics['nearest_variable_star'] = vstar.get_name()
                diagnostics['angular_separation_variable'] = closest_separation_deg
                diagnostics['nearest_variable_type'] = vstar.type

            logger.info('Identified a variable star close to target ' + str(target.pk))

    return diagnostics

# def check_external_variable_catalog(target):
# Future code to check an extended external catalog will go here

def calc_periodogram(target, diagnostics):
    """
    Function to calculate the Lomb-Scargle periodogram for a Source's full lightcurve
    """

    datasets = data_utils.get_full_lightcurve(target, bandpass='Roman_F146')
    lightcurve = datasets.get('Roman_F146')

    if lightcurve is None or len(lightcurve) < 10:
        logger.info(
            'Skipping periodogram for ' + target.name
            + ': fewer than 10 Roman_F146 datapoints available'
        )
        return diagnostics

    frequency, power = LombScargle(lightcurve[:,0], lightcurve[:,1]).autopower()

    max_peak = power.max()
    best_frequency = frequency[np.argmax(power)]
    period = 1.0/best_frequency

    diagnostics['max_peak_periodogram'] = max_peak
    diagnostics['period'] = period

    return diagnostics
