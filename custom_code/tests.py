from django.test import TestCase
from custom_code.models import Event
from custom_code.management.commands import data_utils
from tom_targets.models import Target
from tom_dataproducts.models import PhotometryReducedDatum
from custom_code.solar_system import query_horizons_for_roman, parse_sbident_response
from custom_code import (pylima_fit_functions, general_fit_functions, utils,
        flare_fit_functions)
import datetime
from astropy.time import Time
from django.utils import timezone
from pyLIMA import telescopes
from pyLIMA.models import PSPL_model, FSPL_model
from pyLIMA.fits import TRF_fit
from pyLIMA import event as mulens_event
from pyLIMA.simulations import simulator
from altaipony.fit_flares import fit_flares
import numpy as np
import pandas as pd
import copy

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

        expected_keys = ['X', 'Y', 'Z', 'VX', 'VY', 'VZ']

        jd_event = self.start_time + self.duration/2.0

        spacecraft_vector = query_horizons_for_roman(jd_event)

        for key in expected_keys:
            assert(key in spacecraft_vector.keys())
            assert(type(spacecraft_vector[key]) == type(1.0))

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

        datasets = data_utils.get_baseline_data(self.event)

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

        assert(type(model_lc), type(np.zeros(2)))
        assert(len(model_lc.lightcurve) >= len(test_event.telescopes[0].lightcurve))

class TestGeneralFitFunctions(TestCase):

    def setUp(self):
        self.test_target, self.test_event, self.ndata, self.nlc, self.datums = create_test_target_with_photometry()

    def test_run_event_straightline_fit(self):

        test_mean_mag = np.array([datum.brightness for datum in self.datums]).mean()

        results = general_fit_functions.run_event_straightline_fit(self.test_event)

        self.assertAlmostEqual(results['coeffs'][0], 0.0, 2)
        self.assertAlmostEqual(results['coeffs'][1], test_mean_mag, 0)

class TestFlareFitFunctions(TestCase):

    def setUp(self):
        self.test_target, self.test_event, self.ndata, self.nlc, self.datums = create_test_target_with_photometry()
        self.pitkin_test_params = np.array([
            400, (self.test_event.start_time + self.test_event.duration/2.0),
            400, 400, 0.5, 0.5
        ])

    def test_fit_flares(self):
        """Test Davenport flare fit function call to Altipony"""
        datasets = data_utils.get_reduced_data(self.test_event)
        lightcurve = data_utils.fetch_lightcurve(datasets)
        flux, flux_err = utils.mag_to_flux(lightcurve[:, 1], lightcurve[:, 2])

        tstarts = [self.test_event.start_time]
        tstops = [self.test_event.start_time + self.test_event.duration]

        expected_keys = [
            'params', 'model', 'n_flares', 'score', 't_peaks', 'fwhms',
            'amplitudes', 't_peak', 'fwhm', 'amplitude', 'fit_type',
            'group_index', 't_range', 'time', 'flux', 'flux_err',
            'posterior_samples'
        ]
        fit_list = fit_flares(lightcurve[:, 0], flux, flux_err, tstarts, tstops,
                        buffer=0.05, max_flares=1, delta_bic=0.0,
                        plot=False, debug_plot=False)
        results = fit_list[0]

        assert(type(fit_list) == type([]))
        for key in expected_keys:
            assert(key in results.keys())
        assert(results['t_peaks'][0] >= self.test_event.start_time)
        assert(results['t_peaks'][0] <= self.test_event.start_time + self.test_event.duration)

    def test_calc_goodness_of_flare_fit(self):
        """Test calculation of fit metrics"""
        datasets = data_utils.get_reduced_data(self.test_event)
        lightcurve = data_utils.fetch_lightcurve(datasets)
        flux, flux_err = utils.mag_to_flux(lightcurve[:, 1], lightcurve[:, 2])

        flux_model_lc = copy.deepcopy(flux)
        nparam = 3  # Davenport flare model

        chisq, red_chisq, bic = flare_fit_functions.calc_goodness_of_flare_fit(
            flux, flux_err, flux_model_lc, nparam
        )

        test_bic = float(nparam) * np.log(len(flux))

        self.assertEqual(chisq, 0.0)
        self.assertEqual(red_chisq, 0.0)
        self.assertAlmostEqual(bic, test_bic, 2)

    def test_run_davenport_flare_fit(self):
        """End-to-end test of the Davenport flare model fitting process"""
        expected_keys = [
            't_peak', 't_peak_error', 'peak_amplitude', 'peak_amplitude_error',
            't_FWHM', 't_FWHM_error', 'chisq', 'red_chisq', 'BIC'
        ]

        results = flare_fit_functions.run_davenport_flare_fit(self.test_event)

        for key in expected_keys:
            assert(key in results.keys())

    def test_pitkin_set_conditions_boundaries(self):
        """Test setting of initial conditions and fit parameter boundaries"""
        datasets = data_utils.get_reduced_data(self.test_event)
        lightcurve = data_utils.fetch_lightcurve(datasets)
        flux, flux_err = utils.mag_to_flux(lightcurve[:, 1], lightcurve[:, 2])
        nwalkers = 50
        expected_keys = [
            't_bounds', 'peak_bounds', 'tau_gaussian_rise_bounds',
            'tau_exponential_decay_bounds'
        ]

        ndim, start_position, boundaries = flare_fit_functions.pitkin_set_conditions_boundaries(
            self.test_event, flux, nwalkers
        )

        assert(type(start_position) == type(np.zeros(2)))
        assert(type(boundaries) == type({}))
        for key in expected_keys:
            assert(key in boundaries.keys())
            assert(len(boundaries[key]) == 2)
        assert(boundaries['t_bounds'] == [
            self.test_event.start_time,
            self.test_event.start_time + self.test_event.duration
        ])

    def test_model_pitkin_flare_lightcurve(self):
        """
        Test generation of a model Pitkin flare lightcurve
        based on model parameters:
        [baseline_flux, t, flux, peak, fwhm, tau_gaussian_rise, tau_exponential_decay]
        """
        datasets = data_utils.get_reduced_data(self.test_event)
        lightcurve = data_utils.fetch_lightcurve(datasets)
        flux, flux_err = utils.mag_to_flux(lightcurve[:, 1], lightcurve[:, 2])

        flare_model = flare_fit_functions.model_pitkin_flare_lightcurve(
            lightcurve[:, 0], self.pitkin_test_params
        )
        mag_flare_model, _, _, _ = utils.flux_to_mag(flare_model, np.ones(len(flare_model)))
        print('MAGS: ', mag_flare_model)

        assert(type(flare_model) == type(np.zeros(2)))
        assert(len(flare_model) == len(lightcurve[:, 0]))

    def test_calc_log_posterior(self):
        """
        Test calculation of the log posterior for a Pitkin flare model
        Params contains:
        [baseline_flux, t, flux, peak, fwhm, tau_gaussian_rise, tau_exponential_decay]
        """

        datasets = data_utils.get_reduced_data(self.test_event)
        lightcurve = data_utils.fetch_lightcurve(datasets)
        flux, flux_err = utils.mag_to_flux(lightcurve[:, 1], lightcurve[:, 2])

        t_bounds = [
            self.test_event.start_time,
            self.test_event.start_time + self.test_event.duration
        ]
        peak_bounds = [0.0001, 100000.0]
        tau_gaussian_rise_bounds = [0.0000001, 1.5]
        tau_exponential_decay_bounds = [0.0000001, 3.0]

        log_posterior = flare_fit_functions.calc_log_posterior(
            self.pitkin_test_params, lightcurve[:,0], flux, flux_err,
            t_bounds, peak_bounds,
            tau_gaussian_rise_bounds, tau_exponential_decay_bounds
        )

        assert(np.isfinite(log_posterior))

    def test_calc_log_prior(self):
        """
        Test calculation of the log prior for a Pitkin flare model;
        requires that the input flare parameters remain within boundaries.
        If this is true, the function returns zero, if not, it returns -Inf
        Params contains:
        [baseline_flux, t, flux, peak, tau_gaussian_rise, tau_exponential_decay]
        """

        t_bounds = [
            self.test_event.start_time,
            self.test_event.start_time + self.test_event.duration
        ]
        peak_bounds = [0.0001, 100000.0]
        tau_gaussian_rise_bounds = [0.0000001, 1.5]
        tau_exponential_decay_bounds = [0.0000001, 3.0]

        # Test all parameters within boundaries
        log_prior = flare_fit_functions.calc_log_prior(
            self.pitkin_test_params, t_bounds, peak_bounds,
            tau_gaussian_rise_bounds, tau_exponential_decay_bounds
        )
        self.assertEqual(log_prior, 0.0)

        # Test each parameter outside boundaries in turn
        for i in [1, 3, 4, 5]:
            params = copy.deepcopy(self.pitkin_test_params)
            params[i] += 200000
            log_prior = flare_fit_functions.calc_log_prior(
                params, t_bounds, peak_bounds,
                tau_gaussian_rise_bounds, tau_exponential_decay_bounds
            )
            self.assertEqual(log_prior, -np.inf)

    def test_calc_log_likelihood(self):
        datasets = data_utils.get_reduced_data(self.test_event)
        lightcurve = data_utils.fetch_lightcurve(datasets)
        flux, flux_err = utils.mag_to_flux(lightcurve[:, 1], lightcurve[:, 2])

        log_likelihood = flare_fit_functions.calc_log_likelihood(
            self.pitkin_test_params, lightcurve[:,0], flux, flux_err
        )

        assert(np.isfinite(log_likelihood))

    def test_run_pitkin_flare_model_fit(self):
        """End-to-end test of Pitkin flare model fit"""

        expected_keys = [
            't_peak', 't_peak_error', 'peak_amplitude', 'peak_amplitude_error',
            'tau_gaussian_rise', 'tau_gaussian_rise_error', 'tau_exponential_decay',
            'tau_exponential_decay_error', 'red_chisq', 'chisq', 'BIC'
        ]

        results = flare_fit_functions.run_pitkin_flare_model_fit(self.test_event)

        for key in expected_keys:
            assert(key in results.keys())
        tmax = self.test_event.start_time + self.test_event.duration
        self.assertTrue(self.test_event.start_time <= results['t_peak'] <= tmax)