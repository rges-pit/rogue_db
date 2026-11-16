from custom_code.models import VariableStar, SourceDiagnostics
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

VARIABLE_STAR_ID_FIELDS = ('ogle_id', 'vvv_id', 'gaia_id', 'moa_id')

# A star that is more than one of something, because it is listed twice, or in more than one typed
# catalog, has all of them in its type and its IDs, joined by this
JOIN_SEPARATOR = '/'

def combine(*values):
    """
    The distinct names among the values, which can each be a name or several joined by JOIN_SEPARATOR,
    as one value, joined and in alphabetical order, so that it's the same whichever order they're given
    in. None if there aren't any.
    """
    names = {name for value in values if value for name in value.split(JOIN_SEPARATOR) if name}
    return JOIN_SEPARATOR.join(sorted(names, key=lambda name: (name.casefold(), name))) or None

def split(value):
    """The names in a value that combine() has joined, or that is just a name"""
    return [name.strip() for name in value.split(JOIN_SEPARATOR) if name.strip()] if value else []

def known_variable_names():
    """
    The names of all the variable stars RogueDB knows of, as a set. A VariableStar can have an ID from
    each of several catalogs (see VARIABLE_STAR_ID_FIELDS), and each one is a name the star is
    known by, so a star with more than one ID contributes all of them, as does an ID that
    is several names joined. Stars are read in a single query, and IDs a star hasn't are skipped.
    """
    names = set()
    for ids in VariableStar.objects.values_list(*VARIABLE_STAR_ID_FIELDS).iterator():
        for value in ids:
            names.update(split(value))
    return names

def known_variable_pks(id_field):
    """
    The stars RogueDB has an ID of in one of the catalogs (id_field is one of VARIABLE_STAR_ID_FIELDS),
    as {ID: primary key}. Each of the names of a star that has several is an ID of it. Names are only
    comparable within the one catalog, so unlike known_variable_names this doesn't pool them.
    """
    pks = {}
    stars = VariableStar.objects.exclude(**{id_field: None}).order_by('pk')
    for value, pk in stars.values_list(id_field, 'pk').iterator():
        for name in split(value):
            pks.setdefault(name, pk)
    return pks

def known_variable_positions():
    """
    Function to extract a list of SkyCoords for all currently known variables
    """

    ras, decs, pks = zip(*VariableStar.objects.order_by('pk').values_list('ra', 'dec', 'pk'))
    positions = SkyCoord(np.array(ras), np.array(decs), frame='icrs', unit=(u.deg, u.deg))

    return positions, np.array(pks)

# def check_external_variable_catalog(target):
# Future code to check an extended external catalog will go here

def calc_periodogram(target, lightcurve, diagnostics):
    """
    Function to calculate the Lomb-Scargle periodogram for a Source's full lightcurve
    """

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

    data_utils.generate_periodogram(target, power, frequency)

    return diagnostics
