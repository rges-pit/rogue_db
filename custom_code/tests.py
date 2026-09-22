from django.test import TestCase
from custom_code.models import Event
from custom_code.management.commands import data_utils
from tom_targets.models import Target
from tom_dataproducts.models import PhotometryReducedDatum
from custom_code.solar_system import query_horizons_for_roman, parse_sbident_response
from custom_code import pylima_fit_functions, general_fit_functions
import datetime
from astropy.time import Time
from django.utils import timezone
from pyLIMA import telescopes
from pyLIMA.models import PSPL_model, FSPL_model
from pyLIMA.fits import TRF_fit
from pyLIMA import event as mulens_event
from pyLIMA.simulations import simulator
import numpy as np

def create_test_target_with_photometry():
    """
    Function to create a test target with photometry and an event
    that occurs within the lightcurve
    """
    t = Target.objects.create(
        name='TestObject',
        classification='Microlensing PSPL',
        category='Microlensing stellar/planet',
        ra = 265.5,
        dec = 17.5
    )
    nlc = 1
    ndata = 100
    mean_mag = 17.0
    start_time = datetime.datetime.strptime('2026-09-01T00:00:00.0', '%Y-%m-%dT%H:%M:%S.%f')
    jd_start_time = Time(start_time).jd
    interval = 15.0 # Minutes between exposures
    datums = [PhotometryReducedDatum(**{
        'target': t,
        'timestamp': timezone.make_aware((start_time + i * datetime.timedelta(minutes=interval)), datetime.timezone.utc),
        'brightness': mean_mag,
        'brightness_error': 0.001,
        'bandpass': 'F146'
    }) for i in range(0, ndata, 1)]
    PhotometryReducedDatum.objects.bulk_create(datums)
    e = Event.objects.create(
        target=t,
        event_id='test_event',
        start_time=jd_start_time + ((20*interval) / (24.0 * 60.0)),
        duration=240 / (24.0 * 60.0)  # Units of days
    )

    return t, e, ndata, nlc, datums

def create_test_pylima_event():
    """
    Funcion to simulate a PyLIMA event
    """
    test_event = mulens_event.Event(ra=265.5, dec=17.5)
    test_event.name = 'Test Target'

    ndata = 100
    data = np.zeros((ndata, 3))
    data[:, 0] = np.linspace(2460000.0, 2460000.0 + float(ndata), ndata)
    data[:, 1].fill(16.0)
    data[:, 2].fill(0.001)

    tel1 = telescopes.Telescope(name='Tel_0',
                                camera_filter='I',
                                lightcurve=data.astype(float),
                                lightcurve_names=['time', 'mag', 'err_mag'],
                                lightcurve_units=['JD', 'mag', 'mag'])
    tel1.ld_gamma = 0.5

    test_event.telescopes.append(tel1)

    test_event.find_survey('Tel_0')
    test_event.check_event()

    pspl = PSPL_model.PSPLmodel(test_event, parallax=['None', 0.],
                                blend_flux_parameter='ftotal')
    pspl.define_model_parameters()

    # t0, u0, tE
    pspl_parameters = [2460050.0, 0.001, 4.0]
    pyLIMA_parameters = pspl.compute_pyLIMA_parameters(pspl_parameters)
    simulator.simulate_lightcurve(pspl, pyLIMA_parameters)

    return test_event, pspl

def create_test_model_fit(test_event, pspl_model):
    """
    Function to generate simulated PyLIMA model_fit output
    """

    model_fit = TRF_fit.TRFfit(pspl_model, loss_function='soft_l1')
    model_fit.fit()

    return model_fit

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
        self.target, self.event, self.ndata, self.ndatasets, self.datums = create_test_target_with_photometry()

    def test_get_baseline_data(self):
        """
        Function to test whether data during an event is removed from
        the lightcurve
        """

        datasets = data_utils.get_baseline_data(self.target)

        self.assertEqual(len(datasets), self.ndatasets)

        for dname, data in datasets.items():
            assert(len(data) < self.ndata)

    def test_get_reduced_data(self):
        """
        Function to test whether just datapoints acquired during
        an event are returned
        """

        datasets = data_utils.get_reduced_data(self.event)

        self.assertEqual(len(datasets), self.ndatasets)

        for dname, data in datasets.items():
            assert(data[0,0] >= self.event.start_time)
            assert(data[0,-1] <= self.event.start_time + self.event.duration)

class TestPyLIMAUtils(TestCase):

    def setUp(self):
        self.target, self.event, self.ndata, self.ndatasets, self.datums = create_test_target_with_photometry()

    def test_pylima_telescopes_from_datasets(self):
        """
        Test that the PyLIMA telescope objects created for an event have
        that event's lightcurve data
        """
        datasets = data_utils.get_reduced_data(self.event)

        test_tel = telescopes.Telescope()

        tel_list = pylima_fit_functions.pylima_telescopes_from_datasets(datasets)

        for tel in tel_list:
            self.assertEqual(type(test_tel), type(tel))
            assert(len(tel.lightcurve) > 0)
            assert(len(tel.lightcurve) < self.ndata)

    def test_gather_model_parameters(self):
        """
        Test the extraction of parameters from a fitted model
        """

        test_event, pspl_model = create_test_pylima_event()

        model_fit = create_test_model_fit(test_event, pspl_model)


        test_param_keys = list(model_fit.fit_parameters.keys())
        test_param_keys += [
            'chi2', 'red_chi2', 'BIC', 'source_magnitude',
            'source_mag_error', 'blend_magnitude', 'blend_mag_error'
        ]

        model_params = pylima_fit_functions.gather_model_parameters(
            test_event, model_fit, True
        )

        for key in test_param_keys:
            assert(key in model_params.keys())

    def test_generate_model_lightcurve(self):
        """
        Test generation of model lightcurves
        """

        test_event, pspl_model = create_test_pylima_event()

        model_fit = create_test_model_fit(test_event, pspl_model)

        model_params = pylima_fit_functions.gather_model_parameters(
            test_event, model_fit, True
        )

        model_lc = pylima_fit_functions.generate_model_lightcurve(
            test_event, model_params, True
        )

        assert(type(model_lc), type(np.zeros((2,2))))
        assert(len(model_lc.lightcurve) >= len(test_event.telescopes[0].lightcurve))

class TestGeneralFitFunctions(TestCase):

    def setUp(self):
        self.test_target, self.test_event, self.ndata, self.nlc, self.datums = create_test_target_with_photometry()

    def test_run_event_straightline_fit(self):

        test_mean_mag = np.array([datum.brightness for datum in self.datums]).mean()

        results = general_fit_functions.run_event_straightline_fit(self.test_event)

        self.assertAlmostEqual(results['coeffs'][0], 0.0, 2)
        self.assertAlmostEqual(results['coeffs'][1], test_mean_mag, 0)