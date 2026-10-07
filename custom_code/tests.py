from django.contrib.auth.models import User
from django.http import QueryDict
from django.test import TestCase, override_settings
from django.urls import reverse
from custom_code.models import Event, EventModel, PSPLModel, PitkinFlareModel, StraightLineModel
from custom_code.filters import CutfileFilterSet, CUTFILE_EVENT_PARAMS, CUTFILE_MODEL_TYPES
from tom_targets.models import Target
from tom_dataproducts.models import PhotometryReducedDatum
from custom_code.solar_system import query_horizons_for_roman, parse_sbident_response
from custom_code import (pylima_fit_functions, general_fit_functions, utils,
                         flare_fit_functions, data_utils, variable_stars, diagnostics)
import datetime
import re
from astropy.time import Time
from django.utils import timezone
from pyLIMA import telescopes
from pyLIMA.models import PSPL_model
from pyLIMA.fits import TRF_fit
from pyLIMA import event as mulens_event
from pyLIMA.simulations import simulator
from altaipony.fit_flares import fit_flares
import numpy as np
import copy

def create_test_target_with_photometry(name='TestObject'):
    """
    Function to create a test target with photometry and an event
    that occurs within the lightcurve
    """
    t = Target.objects.create(
        name=name,
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
        'bandpass': 'Roman_F146',
        'source_name': 'Roman_F146'
    }) for i in range(0, ndata, 1)]
    PhotometryReducedDatum.objects.bulk_create(datums)
    e = Event.objects.create(
        target=t,
        event_id='test_event',
        start_time=jd_start_time + ((20*interval) / (24.0 * 60.0)),
        duration=240 / (24.0 * 60.0),  # Units of days
        peak_mag=16.0
    )

    return t, e, ndata, nlc, datums

def create_test_target_with_gaussian():
    """
    Function to create a test target with photometry and an event
    that occurs within the lightcurve, which is approximated by a Gaussian
    """
    t = Target.objects.create(
        name='TestObject2',
        classification='Microlensing PSPL',
        category='Microlensing stellar/planet',
        ra = 265.5,
        dec = 17.5
    )
    nlc = 1
    ndata = 100
    mean_mag = 17.0
    start_time = datetime.datetime.strptime('2026-08-01T00:00:00.0', '%Y-%m-%dT%H:%M:%S.%f')
    jd_start_time = Time(start_time).jd
    interval = 15.0 # Minutes between exposures
    duration = 240 # minutes
    rng = np.random.default_rng(seed=42)  # Setting seed for reproducibility
    gaussian_values = rng.normal(loc=mean_mag, scale=duration / (24.0 * 60.0), size=ndata)
    datums = [PhotometryReducedDatum(**{
        'target': t,
        'timestamp': timezone.make_aware((start_time + i * datetime.timedelta(minutes=interval)), datetime.timezone.utc),
        'brightness': gaussian_values[i],
        'brightness_error': 0.001,
        'bandpass': 'Roman_F146',
        'source_name': 'Roman_F146'
    }) for i in range(0, ndata, 1)]
    PhotometryReducedDatum.objects.bulk_create(datums)
    e = Event.objects.create(
        target=t,
        event_id='test_event2',
        start_time=jd_start_time + ((20*interval) / (24.0 * 60.0)),
        duration=duration / (24.0 * 60.0)  # Units of days
    )

    return t, e, ndata, nlc, datums

def create_event_set(nevents=100):
    """
    Function to simulate a set of events for a set of targets with random parameters

    Parameters:
        nevents  int  Number of events to simulate

    Returns:
        target_list  List of Target objects
        event_list  List of Event objects
        corr_idx    List of indicies of the correlated events
    """

    start_time = datetime.datetime.strptime('2026-08-01T00:00:00.0', '%Y-%m-%dT%H:%M:%S.%f')
    jd_start_time = Time(start_time).jd
    rng = np.random.default_rng(seed=42)  # Setting seed for reproducibility

    # Randomly distributed set of events - note units must be in seconds
    ra = rng.normal(loc=256.5*3600.0, scale=60.0, size=nevents)
    dec = rng.normal(loc=17.5*3600.0, scale=60.0, size=nevents)
    times = rng.normal(loc=jd_start_time*3600.0*24, scale=60.0*8.0, size=nevents)

    # Correlated set of events - units in seconds
    ncorr = 10
    ra2 = rng.normal(loc=256.6*3600.0, scale=1, size=ncorr)
    dec2 = rng.normal(loc=18.5*3600.0, scale=1, size=ncorr)
    times2 = [jd_start_time*3600.0*24]*ncorr

    ra = np.append(ra, ra2)
    dec = np.append(dec, dec2)
    times = np.append(times, times2)
    nevents += ncorr
    corr_idx = np.arange(0, nevents, 1)
    corr_idx = corr_idx[(corr_idx >= nevents-ncorr)]

    target_list = []
    event_list = []
    for i in range(0, nevents, 1):
        t = Target.objects.create(
            name='test_target' + str(i),
            classification='Microlensing PSPL',
            category='Microlensing stellar/planet',
            ra=ra[i],
            dec=dec[i]
        )
        e = Event.objects.create(
            target=t,
            event_id='test_event' + str(i),
            start_time=times[i],
            duration=1.0
        )
        target_list.append(t)
        event_list.append(e)

    return target_list, event_list, corr_idx

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
        self.test_target2, self.test_event2, self.ndata2, self.nlc2, self.datums2 = create_test_target_with_gaussian()

    def test_run_event_straightline_fit(self):

        test_mean_mag = np.array([datum.brightness for datum in self.datums]).mean()

        results = general_fit_functions.run_event_straightline_fit(self.test_event)

        self.assertAlmostEqual(results['coeffs'][0], 0.0, 2)
        self.assertAlmostEqual(results['coeffs'][1], test_mean_mag, 0)

    def test_calc_coverage(self):

        frac_cover = general_fit_functions.calc_coverage(self.test_event)

        assert(type(frac_cover) == type(1.0))
        self.assertAlmostEqual(frac_cover, 1.0, 1)

    def test_calc_symmetry(self):

        skew = general_fit_functions.calc_symmetry(self.test_event2)

        assert(type(skew) == type(1.0))
        assert(skew < 1.0)

    def test_calc_npoints_above_baseline(self):

        # Reset the start_time and duration of the test event to the start
        # for easier array handling
        self.test_event.start_time = Time(self.datums[0].timestamp).jd
        self.test_event.duration = Time(self.datums[51].timestamp).jd - Time(self.datums[0].timestamp).jd

        # Create two-level test lightcurves
        high_points = 50
        full_lightcurve = np.empty((self.ndata,3))
        full_lightcurve[:,0] = [Time(rd.timestamp).jd for rd in self.datums]
        full_lightcurve[0:high_points,1] = 16.0
        full_lightcurve[high_points+1:,1] = 20.0
        full_lightcurve[:,2] = 0.001
        baseline_lightcurve = full_lightcurve[high_points+1:,:]

        npoints = diagnostics.calc_npoints_above_baseline(
            self.test_event,
            baseline_lightcurve,
            full_lightcurve
        )

        assert(npoints == high_points)

class TestFlareFitFunctions(TestCase):

    def setUp(self):
        self.test_target, self.test_event, self.ndata, self.nlc, self.datums = create_test_target_with_photometry()
        # [baseline_flux, t_peak, peak_amplitude, tau_gaussian_rise, tau_exponential_decay]
        self.pitkin_test_params = np.array([
            400, (self.test_event.start_time + self.test_event.duration/2.0),
            400, 0.5, 0.5
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
        [baseline_flux, t, peak, tau_gaussian_rise, tau_exponential_decay]
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
        [baseline_flux, t, peak, tau_gaussian_rise, tau_exponential_decay]
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
        [baseline_flux, t, peak, tau_gaussian_rise, tau_exponential_decay]
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
        for i in [1, 2, 3, 4]:
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

class TestVariableStars(TestCase):

    def setUp(self):
        self.test_target, self.test_event, self.ndata, self.nlc, self.datums = create_test_target_with_photometry()

    def test_calc_periodogram(self):

        variable_stars.calc_periodogram(self.test_target)

        assert(self.test_target.max_peak_periodogram != 0.0)
        assert(self.test_target.period != 0.0)

class TestMultiEventDiagnostics(TestCase):

    def setUp(self):
        self.test_target, self.test_event, self.ndata, self.nlc, self.datums = create_test_target_with_photometry()
        self.test_target2, self.test_event2, self.ndata2, self.nlc2, self.datums2 = create_test_target_with_photometry('TestObject2')
        self.test_target3, self.test_event3, self.ndata3, self.nlc3, self.datums3 = create_test_target_with_photometry('TestObject3')
        Event.objects.filter(pk=self.test_event2.pk).update(target=self.test_target, start_time=self.test_event2.start_time+0.3)
        Event.objects.filter(pk=self.test_event3.pk).update(target=self.test_target, start_time=self.test_event3.start_time+0.5)
        self.test_event2 = Event.objects.get(pk=self.test_event2.pk)
        self.test_event3 = Event.objects.get(pk=self.test_event3.pk)

    def test_second_peak_diagnostics(self):

        event_list = list(Event.objects.filter(target=self.test_target))

        diagnostics.second_peak_diagnostics(self.test_event, event_list)

        test_event = Event.objects.get(pk=self.test_event.pk)

        midpoint = self.test_event.start_time + self.test_event.duration/2.0
        midpoint2 = self.test_event2.start_time + self.test_event2.duration/2.0
        dt = abs(midpoint - midpoint2)
        self.assertAlmostEqual(test_event.time_to_second_peak, dt, 2)
        self.assertAlmostEqual(test_event.second_peak_mag, self.test_event2.peak_mag)

    def test_link_events(self):
        target_list, events_list, corr_idx = create_event_set()

        diagnostics.link_events(events_list)

        for i in corr_idx:
            e = events_list[i]
            e = Event.objects.get(pk=e.pk)
            assert(e.Nlinked_events == len(corr_idx) - 1)


class TestCutfileSearch(TestCase):
    """
    The cutfile query: EventModels of one type, selected by thresholds on their own
    parameters, their Event's and their Source's.
    """

    def setUp(self):
        # Two sources, each with one event carrying a PSPL model, a Pitkin flare model,
        # and a straight line and a baseline fit (both stored as StraightLineModels)
        specs = [
            # name, ra, variable type, event duration, PSPL tE, chisq, straight line gradient
            ('CutfileA', 100.0, 'RRLyr', 2.0, 0.2, 50.0, -0.5),
            ('CutfileB', 200.0, 'Mira', 6.0, 5.0, 500.0, 0.5),
        ]
        for name, ra, variable_type, duration, tE, chisq, gradient in specs:
            target = Target.objects.create(name=name, ra=ra, dec=10.0, nearest_variable_type=variable_type)
            event = Event.objects.create(target=target, event_id=name + '-1', start_time=2460000.0, duration=duration)
            PSPLModel.objects.create(event=event, model_type='PSPL microlensing', tE=tE, chisq=chisq)
            PitkinFlareModel.objects.create(event=event, model_type='Pitkin flare', t_peak=2460000.5, chisq=chisq)
            StraightLineModel.objects.create(event=event, model_type='Straight line', gradient=gradient, intercept=20.0)
            StraightLineModel.objects.create(event=event, model_type='Baseline', gradient=99.0, intercept=20.0)

    def search(self, query_string=''):
        filterset = CutfileFilterSet(QueryDict(query_string), queryset=EventModel.objects.all())
        return sorted(filterset.qs.values_list('event__target__name', flat=True))

    def test_event_parameters_cover_event_model_except_thumbnail(self):
        names = {p.name for p in CUTFILE_EVENT_PARAMS}
        expected = {f.name for f in Event._meta.get_fields() if f.concrete} - {'id', 'target', 'thumbnail'}
        self.assertEqual(names, expected)
        self.assertIn('peak_mag', names)

    def model_types_found(self, query_string):
        filterset = CutfileFilterSet(QueryDict(query_string), queryset=EventModel.objects.all())
        return set(filterset.qs.values_list('model_type', flat=True))

    def test_defaults_to_all_model_types(self):
        all_slugs = [mt.slug for mt in CUTFILE_MODEL_TYPES]
        for query_string in ['', 'model_type=not-a-model-type']:
            filterset = CutfileFilterSet(QueryDict(query_string), queryset=EventModel.objects.all())
            self.assertEqual([mt.slug for mt in filterset.selected_model_types], all_slugs)
            self.assertEqual(self.model_types_found(query_string),
                             {'PSPL microlensing', 'Pitkin flare', 'Straight line', 'Baseline'})

        # Unknown types are dropped from a list that has valid ones
        filterset = CutfileFilterSet(QueryDict('model_type=fspl&model_type=bogus'), queryset=EventModel.objects.all())
        self.assertEqual([mt.slug for mt in filterset.selected_model_types], ['fspl'])

    def test_selects_model_types(self):
        self.assertEqual(self.model_types_found('model_type=pitkin_flare'), {'Pitkin flare'})
        self.assertEqual(self.model_types_found('model_type=pitkin_flare&model_type=pspl'),
                         {'Pitkin flare', 'PSPL microlensing'})

    def test_searches_several_model_types_at_once(self):
        both = 'model_type=pspl&model_type=pitkin_flare'
        self.assertEqual(self.search(both), ['CutfileA', 'CutfileA', 'CutfileB', 'CutfileB'])

        # A type's thresholds apply to its own models only: here the PSPL models are cut to
        # A's, while Pitkin flare has no thresholds so contributes both of its models
        self.assertEqual(self.search(both + '&pspl_tE_max=1'), ['CutfileA', 'CutfileA', 'CutfileB'])
        self.assertEqual(self.model_types_found(both + '&pspl_tE_max=1&pitkin_flare_t_peak_max=1'),
                         {'PSPL microlensing'})

        # ...and a model is found if it meets its own type's thresholds: B's PSPL and both Pitkin
        self.assertEqual(self.search(both + '&pspl_tE_min=1&pitkin_flare_t_peak_min=2460000'),
                         ['CutfileA', 'CutfileB', 'CutfileB'])

        # Source, event and fit-statistic thresholds apply to every model found
        self.assertEqual(self.search(both + '&model_chisq_max=100'), ['CutfileA', 'CutfileA'])
        self.assertEqual(self.search('source_ra_max=150'), ['CutfileA'] * 4)
        self.assertEqual(self.search(both + '&pspl_tE_max=1&source_ra_min=150'), ['CutfileB'])

        # Thresholds for a type that isn't searched are ignored
        self.assertEqual(self.search('model_type=pspl&pitkin_flare_t_peak_max=1'), ['CutfileA', 'CutfileB'])

    def test_straight_line_parameters(self):
        self.assertEqual(self.search('model_type=straight_line'), ['CutfileA', 'CutfileB'])
        self.assertEqual(self.search('model_type=straight_line&straight_line_gradient_max=0'), ['CutfileA'])
        self.assertEqual(self.search('model_type=straight_line&straight_line_gradient_min=0'), ['CutfileB'])
        # Baseline fits share the table (here with gradient 99) but aren't straight line models
        self.assertEqual(self.search('model_type=straight_line&straight_line_gradient_min=50'), [])

    def test_baseline_parameters(self):
        self.assertEqual(self.model_types_found('model_type=baseline'), {'Baseline'})
        self.assertEqual(self.search('model_type=baseline'), ['CutfileA', 'CutfileB'])
        self.assertEqual(self.search('model_type=baseline&baseline_gradient_min=50'), ['CutfileA', 'CutfileB'])
        self.assertEqual(self.search('model_type=baseline&baseline_gradient_max=50'), [])
        # Its thresholds are its own: the straight line type's don't select baseline fits
        self.assertEqual(self.search('model_type=baseline&straight_line_gradient_max=0'), ['CutfileA', 'CutfileB'])
        # ...and alongside straight line, each type is judged by its own: A's straight line
        # (gradient -0.5) and both baselines (99)
        self.assertEqual(
            self.search('model_type=straight_line&model_type=baseline&straight_line_gradient_max=0'
                        '&baseline_gradient_min=50'),
            ['CutfileA', 'CutfileA', 'CutfileB'])

    def test_model_parameter_thresholds(self):
        self.assertEqual(self.search('model_type=pspl&pspl_tE_max=1'), ['CutfileA'])
        self.assertEqual(self.search('model_type=pspl&pspl_tE_min=1'), ['CutfileB'])
        # chisq lives on the EventModel base table, shared by every model type
        self.assertEqual(self.search('model_type=pspl&model_chisq_max=100'), ['CutfileA'])
        self.assertEqual(self.search('model_type=pitkin_flare&model_chisq_min=100'), ['CutfileB'])

    def test_event_and_source_thresholds(self):
        self.assertEqual(self.search('model_type=pspl&event_duration_min=4'), ['CutfileB'])
        self.assertEqual(self.search('model_type=pspl&source_ra_max=150'), ['CutfileA'])
        self.assertEqual(self.search('model_type=pspl&source_nearest_variable_type=mira'), ['CutfileB'])  # case-insensitive "contains"
        self.assertEqual(self.search('model_type=pspl&event_event_id=CutfileA'), ['CutfileA'])

    def test_sections_combine(self):
        self.assertEqual(self.search('model_type=pspl&source_ra_max=150&event_duration_max=3&pspl_tE_max=1'), ['CutfileA'])
        self.assertEqual(self.search('model_type=pspl&source_ra_max=150&event_duration_min=4'), [])

    def test_other_model_types_values_are_ignored(self):
        self.assertEqual(
            self.search('model_type=pspl&pitkin_flare_t_peak_min=9999999&fspl_rho_min=5'),
            ['CutfileA', 'CutfileB'],
        )

    def test_layout_expands_sections_with_values(self):
        filterset = CutfileFilterSet(QueryDict('event_duration_min=4'), queryset=EventModel.objects.all())
        layout = filterset.layout()
        self.assertEqual({s['id']: s['open'] for s in layout['sections']},
                         {'source': False, 'event': True, 'model': False})

        # With nothing set the model section is open, rather than a form of all-closed sections
        layout = CutfileFilterSet(None, queryset=EventModel.objects.all()).layout()
        self.assertEqual([s['id'] for s in layout['sections'] if s['open']], ['model'])

    def test_search_limited_to_models_available_as_of_a_moment(self):
        # CutfileA's models were made in 2025, CutfileB's in 2026
        EventModel.objects.filter(event__target__name='CutfileA').update(
            created_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc))
        EventModel.objects.filter(event__target__name='CutfileB').update(
            created_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc))

        self.assertEqual(self.search('model_type=pspl'), ['CutfileA', 'CutfileB'])
        for as_of in ['2025-06-01T00:00:00Z', '2025-06-01T00:00:00+00:00', '2025-06-01T02:00:00+02:00']:
            query = QueryDict(mutable=True)
            query.update({'model_type': 'pspl', 'as_of': as_of})
            self.assertEqual(self.search(query.urlencode()), ['CutfileA'], as_of)
        self.assertEqual(self.search('model_type=pspl&as_of=2026-06-01T00:00:00Z'), ['CutfileA', 'CutfileB'])
        self.assertEqual(self.search('model_type=pspl&as_of=2024-06-01T00:00:00Z'), [])

        # The cutoff applies alongside the parameter thresholds, and to every model type
        self.assertEqual(self.search('model_type=pspl&as_of=2026-06-01T00:00:00Z&pspl_tE_max=1'), ['CutfileA'])
        self.assertEqual(self.search('model_type=straight_line&as_of=2025-06-01T00:00:00Z'), ['CutfileA'])

        # A model made after the cutfile doesn't change what it finds
        before = self.search('model_type=pspl&as_of=2026-06-01T00:00:00Z')
        event = Event.objects.get(event_id='CutfileA-1')
        PSPLModel.objects.create(event=event, model_type='PSPL microlensing', tE=0.1, chisq=1.0)
        self.assertEqual(self.search('model_type=pspl&as_of=2026-06-01T00:00:00Z'), before)

    @override_settings(TOM_MFA_REQUIRED=None)
    def test_view_as_of(self):
        EventModel.objects.filter(event__target__name='CutfileA').update(
            created_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc))
        self.client.force_login(User.objects.create_user('cutfile_user'))
        url = reverse('cutfiles:list')

        # Every results page is stamped with when it was read, for saving a cutfile from it
        response = self.client.get(url + '?model_type=pspl')
        self.assertIsNone(response.context['as_of'])
        searched_at = response.context['searched_at']
        self.assertContains(response, 'data-searched-at="%s"' % searched_at)
        self.assertGreater(datetime.datetime.fromisoformat(searched_at), datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc))
        self.assertContains(response, 'name="as_of"')
        self.assertNotContains(response, 'available up to')

        # A cutfile's search is limited to its moment, and says so; and so does its export
        query = '?model_type=pspl&as_of=2025-06-01T00:00:00%2B00:00'
        response = self.client.get(url + query, headers={'HX-Request': 'true'})
        self.assertContains(response, '1 event model available up to 2025-06-01 00:00 UTC')
        self.assertContains(response, 'CutfileA')
        self.assertNotContains(response, 'CutfileB')

        data = self.client.get(url + query + '&export=json').json()
        self.assertEqual(data['as_of'], '2025-06-01T00:00:00Z')
        self.assertEqual(data['criteria'], {})
        self.assertEqual([r['source']['name'] for r in data['results']], ['CutfileA'])
        self.assertIsNone(self.client.get(url + '?model_type=pspl&export=json').json()['as_of'])

    @override_settings(TOM_MFA_REQUIRED=None)
    def test_results_table_columns(self):
        event = Event.objects.get(event_id='CutfileA-1')
        event.thumbnail = 'event_thumbnails/cutfile_a.png'
        event.duration = 2.0456
        event.save()
        EventModel.objects.filter(event=event, model_type='PSPL microlensing').update(chisq=50.126, BIC=12.3456)
        self.client.force_login(User.objects.create_user('cutfile_user'))

        response = self.client.get(reverse('cutfiles:list') + '?model_type=pspl&pspl_tE_max=1',
                                   headers={'HX-Request': 'true'})

        table = response.context['table']
        self.assertEqual([c.verbose_name for c in table.columns],
                         ['Source name', 'Thumbnail', 'Event ID', 'Duration [d]', 'Model type', 'Chisq', 'BIC'])
        self.assertContains(response, '<img src="%s"' % event.thumbnail.url)
        self.assertContains(response, 'href="%s"' % reverse('events:detail', kwargs={'pk': event.pk}))
        self.assertContains(response, 'CutfileA-1')

        # Duration, chisq and BIC are shown to 2 decimal places
        self.assertContains(response, '<td >2.05</td>', html=False)
        self.assertContains(response, '<td >50.13</td>', html=False)
        self.assertContains(response, '<td >12.35</td>', html=False)

        # The columns sort by the Event's values
        response = self.client.get(reverse('cutfiles:list') + '?model_type=pspl&sort=-duration',
                                   headers={'HX-Request': 'true'})
        self.assertEqual([r.record.event.event_id for r in response.context['table'].page.object_list],
                         ['CutfileB-1', 'CutfileA-1'])

    @override_settings(TOM_MFA_REQUIRED=None)
    def test_export_json(self):
        self.client.force_login(User.objects.create_user('cutfile_user'))
        url = reverse('cutfiles:list')

        # The results page offers the download for the search on show
        response = self.client.get(url + '?model_type=pspl&pspl_tE_max=1&sort=chisq&page=1')
        export_url = response.context['export_url']
        self.assertEqual(QueryDict(export_url.lstrip('?')).dict(),
                         {'model_type': 'pspl', 'pspl_tE_max': '1', 'export': 'json'})
        self.assertContains(response, 'Download JSON')

        response = self.client.get(url + export_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('attachment; filename="cutfile_results.json"', response['Content-Disposition'])
        data = response.json()
        self.assertEqual(data['model_types'], ['pspl'])
        self.assertEqual(data['criteria'], {'pspl_tE_max': '1'})
        self.assertEqual(data['count'], 1)

        # The source, its event and the PSPL model, with the model's own parameters
        result = data['results'][0]
        self.assertEqual(result['source']['name'], 'CutfileA')
        self.assertEqual(result['source']['ra'], 100.0)
        self.assertEqual(result['source']['nearest_variable_type'], 'RRLyr')
        self.assertEqual(result['event']['event_id'], 'CutfileA-1')
        self.assertEqual(result['event']['duration'], 2.0)
        self.assertNotIn('thumbnail', result['event'])
        self.assertEqual(result['model']['tE'], 0.2)
        self.assertEqual(result['model']['chisq'], 50.0)
        self.assertEqual(result['model']['model_type'], 'PSPL microlensing')
        self.assertNotIn('corner_plot', result['model'])

        # Every match is exported, whatever the table's page size; and a model type's own columns
        response = self.client.get(url + '?model_type=straight_line&export=json')
        data = response.json()
        self.assertEqual(data['count'], 2)
        self.assertEqual(sorted(r['model']['gradient'] for r in data['results']), [-0.5, 0.5])
        self.assertEqual({r['model']['model_type'] for r in data['results']}, {'Straight line'})

        # Several model types in one file, each with its own parameters
        response = self.client.get(url + '?model_type=pspl&model_type=straight_line&export=json&pspl_tE_max=1')
        data = response.json()
        self.assertEqual(data['model_types'], ['pspl', 'straight_line'])
        self.assertEqual(data['count'], 3)
        by_type = {}
        for r in data['results']:
            by_type.setdefault(r['model']['model_type'], []).append(r['model'])
        self.assertEqual(sorted(by_type), ['PSPL microlensing', 'Straight line'])
        self.assertEqual([m['tE'] for m in by_type['PSPL microlensing']], [0.2])
        self.assertTrue(all('gradient' in m and 'tE' not in m for m in by_type['Straight line']))

        # Straight line and Baseline fits share a table but are exported as the types they are
        data = self.client.get(url + '?model_type=straight_line&model_type=baseline&export=json').json()
        self.assertEqual(data['count'], 4)
        self.assertEqual(sorted((r['model']['model_type'], r['model']['gradient']) for r in data['results']),
                         [('Baseline', 99.0), ('Baseline', 99.0), ('Straight line', -0.5), ('Straight line', 0.5)])

    def test_export_json_requires_login(self):
        response = self.client.get(reverse('cutfiles:list') + '?model_type=pspl&export=json')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/accounts/login/'))

    def test_view_requires_login(self):
        url = reverse('cutfiles:list') + '?model_type=pspl'

        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/accounts/login/'))

        response = self.client.get(url, headers={'HX-Request': 'true'})
        self.assertTrue(response['HX-Redirect'].startswith('/accounts/login/'))
        self.assertNotContains(response, 'CutfileA')

    # The project requires every user to enrol in 2FA (TOM_MFA_REQUIRED='all'), which
    # would redirect this test user to the enrolment page; not what's being tested here.
    @override_settings(TOM_MFA_REQUIRED=None)
    def test_view(self):
        self.client.force_login(User.objects.create_user('cutfile_user'))
        url = reverse('cutfiles:list')

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        for text in ['Upload file', 'Query form', 'Results', 'Source parameters',
                     'Event parameters', 'Event model parameters']:
            self.assertContains(response, text)
        self.assertEqual(response.context['initial_tab'], 'query')
        # The upload tab can run the same search as the query form, being tied to its form
        self.assertContains(response, 'type="submit" form="filter-form"')
        # Both tabs can clear the form
        self.assertContains(response, 'onclick="clearCriteria()"', count=2)

        # Every model type is searched unless the form says otherwise
        self.assertEqual(len(response.context['filter'].selected_model_types), len(CUTFILE_MODEL_TYPES))
        self.assertContains(response, 'type="checkbox" name="model_type"', count=len(CUTFILE_MODEL_TYPES))
        self.assertEqual(len(re.findall(r'id="include-\w+" checked', response.content.decode())),
                         len(CUTFILE_MODEL_TYPES))

        # A search from the form is an HTMX request, answered with just the table
        response = self.client.get(url + '?model_type=pspl&pspl_tE_max=1', headers={'HX-Request': 'true'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1 event model')
        self.assertContains(response, 'CutfileA')
        self.assertNotContains(response, 'CutfileB')
        self.assertNotContains(response, '<html')

        # Sorting and paging keep every model type searched
        response = self.client.get(url + '?model_type=pspl&model_type=fspl', headers={'HX-Request': 'true'})
        self.assertContains(response, 'model_type=pspl&amp;model_type=fspl&amp;sort=')

        # ...while a search URL loaded directly opens on the results
        response = self.client.get(url + '?model_type=fspl')
        self.assertEqual(response.context['initial_tab'], 'results')
