from custom_code.models import Event
import requests
from astropy.coordinates import SkyCoord
from astropy import units as u
import logging

logger = logging.getLogger(__name__)

def find_moving_objects_near_event(event, radius=2):
    """
    Function to query JPL's Small Body Identification Tool to see if there are any
    known asteroids or comets nearby that may have caused the Event
    """

    # First get Roman's vector at the time of the Event.
    # Note the minimum time is Roman's launch date of August 30, 2026, at 7:26 a.m. EDT
    jd_event = event.start_time + event.duration/2.0
    spacecraft_vector = query_horizons_for_roman(jd_event)

    # Now we can query JPL's Small Bodies Identification Tool for any asteroids and comets
    # close to our Target coordinates at this time

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

    object_list = []

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
        print(content)
        if 'data_second_pass' in content.keys():
            for entry in content['data_second_pass']:
                moving_bodies = SkyCoord()  # For the list of entries
                source = SkyCoord(target.ra, target.dec, frame='icrs', unit=(u.deg, u.deg))
                separation = source.separation(moving_bodies)

                # And find minimum as for variables
