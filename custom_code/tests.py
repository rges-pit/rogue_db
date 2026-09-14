from django.test import TestCase
from custom_code.models import Event
from custom_code.management.commands import data_utils
from tom_targets.models import Target
from tom_dataproducts.models import PhotometryReducedDatum
from custom_code.solar_system import query_horizons_for_roman, parse_sbident_response
from django.utils import text, timezone
from datetime import datetime, timedelta, tzinfo
from astropy.time import Time
import pytz

class TestSolarSystemFunctions(TestCase):
    def setUp(self):
        self.start_time = 2461293.5
        self.duration = 0.5
        self.ra = 262.71041667
        self.dec = -28.50847222
        self.spacecraft_vector = {
            'X': 9.874138849751044E-01,
            'Y': -2.258220711155050E-01,
            'Z': -1.101490336117022E-03,
            'VX': 3.812111312462203E-03,
            'VY': 1.663650976978895E-02,
            'VZ': -4.293360433293914E-05
        }
    def test_query_horizons_for_roman(self):

        expected_vector = {
            'X': 9.874138849751044E-01,
            'Y': -2.258220711155050E-01,
            'Z': -1.101490336117022E-03,
            'VX': 3.812111312462203E-03,
            'VY': 1.663650976978895E-02,
            'VZ':-4.293360433293914E-05
        }

        jd_event = self.start_time + self.duration/2.0

        spacecraft_vector = query_horizons_for_roman(jd_event)

        self.assertEqual(spacecraft_vector, expected_vector)

    def test_parse_sbident_response(self):

        content = {"data_second_pass": [
            ["10193 Nishimoto (1996 PR1)", "10:16:58.22", "+10 28'34.3\"", "2.E3", "814.", "1951.", "19.4",
             "-2.564E+01", "1.035E+01"],
            ["15319 (1993 NU1)", "10:19:52.66", "+10 06'12.0\"", "4.E3", "-528.", "4422.", "18.5", "-3.293E+01",
             "1.591E+01"],
        ]}
        expected_name = '10193 Nishimoto (1996 PR1)'
        expected_sep = 1951.0

        closest_name, closest_sep = parse_sbident_response(content)

        self.assertEqual(expected_name, closest_name)
        self.assertEqual(expected_sep, closest_sep)

class TestDataUtils(TestCase):
    def setUp(self):
        self.target = Target.objects.create(
            name='TestObject',
            classification='Microlensing PSPL',
            category='Microlensing stellar/planet',
        )
        self.ndata = 100
        self.mean_mag = 17.0
        self.start_time = datetime.strptime('2026-09-01T00:00:00.0', '%Y-%m-%dT%H:%M:%S.%f')
        self.jd_start_time = Time(self.start_time)
        self.datums = [PhotometryReducedDatum(**{
            'target': self.target,
            'timestamp': self.start_time + i*timedelta(minutes=15.0),
            'brightness': self.mean_mag,
            'brightness_error': 0.001,
            'bandpass': 'W213'
        }) for i in range(0,self.ndata,1)]
        PhotometryReducedDatum.objects.bulk_create(self.datums)
        self.event = Event.objects.create(
            target=self.target,
            event_id='test_event',
            start_time=self.jd_start_time.jd + 20*(15.0/24.0*60.0),
            duration=60/(24.0*60.0) # Units of days
        )

    def test_get_baseline_data(self):

        datasets = data_utils.get_baseline_data(self.target)

