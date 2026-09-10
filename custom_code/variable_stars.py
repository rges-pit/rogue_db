from custom_code.models import VariableStar, RogueTarget
from astropy.coordinates import SkyCoord
from astropy import units as u
import numpy as np
import logging

logger = logging.getLogger(__name__)

def find_nearest_rges_variable_catalog(target, radius=2):
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

        # Update Target with information about the nearest variable star, if the nearest
        # star is closer than the search radius
        if closest_separation_deg <= radius:  # In degrees
            vstar = qs[closest_idx]
            RogueTarget.objects.filter(pk=target.pk).update(
                nearest_variable_star=vstar.get_name(),
                angular_separation_variable=closest_separation_deg,
            )
            logger.info('Identified a variable star close to target ' + str(target.pk))

# def check_external_variable_catalog(target):
# Future code to check an extended external catalog will go here