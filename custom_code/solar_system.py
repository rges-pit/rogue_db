from custom_code.models import Event
import requests
from astropy.coordinates import SkyCoord
from astropy import units as u
import numpy as np
import logging

logger = logging.getLogger(__name__)

def find_moving_objects_near_event(event, radius=2.0):
    """
    Function to query JPL's Small Body Identification Tool to see if there are any
    known asteroids or comets nearby that may have caused the Event

    Parameters:
        event   Event object
        radius  float   Search radius in arcsec
    """

    # First get Roman's vector at the time of the Event.
    # Note the minimum time is Roman's launch date of August 30, 2026, at 7:26 a.m. EDT
    jd_event = event.start_time + event.duration/2.0
    spacecraft_vector = query_horizons_for_roman(jd_event)

    # Now we can query JPL's Small Bodies Identification Tool for any asteroids and comets
    # close to our Target coordinates at this time
    closest_name, closest_separation = query_sbident_for_event(
        event.target.ra, event.target.dec, jd_event, spacecraft_vector,
        fov_width=radius/3600.0
    )

    if closest_name:
        Event.objects.filter(pk=event.pk).update(
            nearest_moving_object=closest_name,
            angular_separation_moving_object=closest_separation/3600.0,  # Stored in deg
        )
        logger.info('Identified a moving object close to event ' + str(event.pk))

def query_horizons_for_roman(jd_event):
    """
    Function to query JPL Horizons to find Roman's position vector for a given time, jd
    """
    horizons_url = 'https://ssd.jpl.nasa.gov/api/horizons.api'

    spacecraft_vector = {'X': None, 'Y': None, 'Z': None, 'VX': None, 'VY': None, 'VZ': None}

    payload = {
        'COMMAND': '-211',  # JPL code for Roman Spacecraft
        'EPHEM_TYPE': 'VECTORS',
        'CENTER': '500@10',  # Solar center; returns Roman's position relative to the Sun directly
        'REF_SYSTEM': 'ICRF',
        'OUT_UNITS': 'AU-D',
        'VEC_TABLE': '2',  # x,y,z,Vx,Vy,Vz format
        'VEC_CORR': 'NONE',
        'TLIST': jd_event,
        'TLIST_TYPE': 'JD',
        'TIME_TYPE': 'UT',
        'OBJ_DATA': 'NO',
        'format': 'json'
    }

    r = requests.get(horizons_url, params=payload)

    if r.status_code == 200:
        content = r.json()

        # Parse the Horizon's vector table format
        for i, line in enumerate(content['result'].split('\n')):
            if ' X = ' in line:
                entries = line.replace('=','').split()
                spacecraft_vector['X'] = float(entries[1])
                spacecraft_vector['Y'] = float(entries[3])
                spacecraft_vector['Z'] = float(entries[5])
            if ' VX= ' in line:
                entries = line.replace('VX=','').replace('VY=','').replace('VZ=','').split()
                spacecraft_vector['VX'] = float(entries[0])
                spacecraft_vector['VY'] = float(entries[1])
                spacecraft_vector['VZ'] = float(entries[2])

    return spacecraft_vector

def query_sbident_for_event(ra, dec, jd_event, spacecraft_vector, fov_width=2.0/3600.0):
    """
    Function to query JPL's Small Body Identification Tool for a list of objects within
    a radius of the given RA and Dec at the given time.
    """

    ssd_url = 'https://ssd-api.jpl.nasa.gov/sb_ident.api'

    closest_name = None
    closest_separation = None

    # Convert the spacecraft vector parameters to a string
    vector = ','.join(
        [str(spacecraft_vector[key]) for key in ['X', 'Y', 'Z', 'VX', 'VY', 'VZ']]
    )

    # Convert the Target coordinates to hexigesimal
    s = SkyCoord(ra, dec, frame='icrs', unit=(u.deg, u.deg))
    ra_str, dec_str = s.to_string(style='hmsdms').split()

    payload = {
        'xobs': vector,
        'obs-time': jd_event,
        'fov-ra-center': ra_str,
        'fov-dec-center': dec_str,
        'fov-ra-hwidth': fov_width,
        'fov-dec-hwidth': fov_width,
        'two-pass': 'true',      # Used for more precise coordinate calculations
        'req-elem': 'false',    # Orbital elements are not required;
    }

    r = requests.get(ssd_url, params=payload)

    if r.status_code == 200:
        content = r.json()

        # Parse the sb_ident's output
        closest_name, closest_separation = parse_sbident_response(content)

    return closest_name, closest_separation

def parse_sbident_response(content):
    """
    Function to parse the list of object IDs and separations
    """

    closest_name = None
    closest_separation = None

    if 'data_second_pass' in content.keys():
        object_names = []
        separations = []
        for entry in content['data_second_pass']:
            object_names.append(entry[0])
            separations.append(float(entry[5]))
        separations = np.array(separations)
        object_names = np.array(object_names)
        closest_idx = int(np.argmin(separations))
        closest_name = object_names[closest_idx]
        closest_separation = separations[closest_idx]

    return closest_name, closest_separation