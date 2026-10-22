from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.http import QueryDict
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import NoReverseMatch, reverse
from custom_code.serializers import MSOSAlertSerializer
from custom_code import tasks, source_functions, solar_system, event_functions
import requests
from django_tasks.signals import task_enqueued
from collections import Counter
from django_tasks.backends.database.models import DBTaskResult
from unittest import mock
from custom_code.models import (Event, EventModel, PSPLModel, PitkinFlareModel, StraightLineModel,
                                DavenportFlareModel, FSPLModel, RGESAlert, SourceDiagnostics)
from custom_code.filters import (CutfileFilterSet, CUTFILE_EVENT_PARAMS, CUTFILE_MODEL_TYPES,
                                 RogueTargetFilterSet, find_row_with)
from tom_targets.models import Target, TargetName
from tom_dataproducts.models import PhotometryReducedDatum, ReducedDatum
from custom_code.templatetags import plotting_functions
from custom_code.solar_system import query_horizons_for_roman, parse_sbident_response
from custom_code import (pylima_fit_functions, general_fit_functions, utils,
                         flare_fit_functions, data_utils, variable_stars, diagnostics)
import datetime
import importlib
import json
from concurrent.futures import ProcessPoolExecutor
import io
import multiprocessing
import os
import subprocess
import sys
import matplotlib
import matplotlib.figure
import posixpath
import tempfile
from io import StringIO
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.template import Context, Template
from django.core.management.base import CommandError
import re
from django.apps import apps as django_apps
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

# The tests log in users who have enrolled in nothing and have no name or email. The project's
# policies for real users (every user enrols in 2FA, and fills in their name and email) would send
# each of them to the page for that, rather than the page being tested.
_policy_overrides = override_settings(TOM_MFA_REQUIRED=None, TOM_REQUIRED_USER_FIELDS=[])


def setUpModule():
    _policy_overrides.enable()


def tearDownModule():
    _policy_overrides.disable()


def create_test_target_with_photometry(name='TestObject'):
    """
    Function to create a test target with photometry and an event
    that occurs within the lightcurve
    """
    t = Target.objects.create(
        name=name,
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
        event_id='test_event' if name == 'TestObject' else 'test_event_' + name,   # Unique, as the database requires
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

    def test_store_flare_model_parameters(self):
        """
        Both flare models are created the first time an event's fit is stored, and
        updated in place after that
        """
        fit = {
            'chisq': 12.5, 'red_chisq': 1.25, 'BIC': 30.0, 'fit_method': 'mcmc',
            'tau': 40.0, 'tau_threshold': 0.4, 't_peak': 2460000.5, 't_peak_error': 0.01,
            'peak_amplitude': 0.8, 'peak_amplitude_error': 0.05,
        }
        cases = [
            (data_utils.store_davenportflare_model_parameters, DavenportFlareModel,
             {'t_FWHM': 0.2, 't_FWHM_error': 0.01}),
            (data_utils.store_pitkinflare_model_parameters, PitkinFlareModel,
             {'tau_gaussian_rise': 0.1, 'tau_gaussian_rise_error': 0.01,
              'tau_exponential_decay': 0.3, 'tau_exponential_decay_error': 0.02}),
        ]
        for store, model_class, extra in cases:
            with self.subTest(model=model_class.__name__):
                results = {**fit, **extra}

                flare = store(self.event, results)
                self.assertEqual(model_class.objects.filter(event=self.event).count(), 1)
                for name, value in results.items():
                    self.assertEqual(getattr(flare, name), value, name)

                results['chisq'], results['tau_threshold'] = 15.0, 0.5
                store(self.event, results)
                flare = model_class.objects.get(event=self.event)
                self.assertEqual((flare.chisq, flare.tau_threshold), (15.0, 0.5))

    def test_store_event_statistics(self):
        """
        The statistics reach the database and the Event instance the caller holds, so that
        a later save() of that instance (as the diagnostics do) doesn't write the old values
        back over them
        """
        results = {'coverage_fraction': 0.85, 'symmetry': 0.4}

        data_utils.store_event_statistics(self.event, results)

        stored = Event.objects.get(pk=self.event.pk)
        self.assertEqual((stored.coverage_fraction, stored.symmetry), (0.85, 0.4))
        self.assertEqual((self.event.coverage_fraction, self.event.symmetry), (0.85, 0.4))

        self.event.delta_chi2_PSPL = 3.0
        self.event.save()
        stored = Event.objects.get(pk=self.event.pk)
        self.assertEqual((stored.coverage_fraction, stored.symmetry, stored.delta_chi2_PSPL), (0.85, 0.4, 3.0))

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

    def test_generate_periodogram(self):
        """
        Function to test that a periodogram is drawn and kept, as a picture, with the source
        """
        frequency = np.linspace(0.001, 10.0, 100)
        power = np.ones(100)

        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            data_utils.generate_periodogram(self.target, power, frequency)

            stored = type(self.target).objects.get(pk=self.target.pk).periodogram
            self.assertTrue(stored.name.startswith('periodograms/'))
            self.assertIn(self.target.name + '_periodogram', stored.name)
            with default_storage.open(stored.name) as image:
                self.assertEqual(image.read(8), b'\x89PNG\r\n\x1a\n')

        # It's a picture: no periodogram is stored as data
        self.assertFalse(ReducedDatum.objects.filter(data_type__startswith='periodogram').exists())

class TestFitStartingValues(TestCase):
    """
    A fit of an event's microlensing model starts from the t0, u0 and tE of its alert. (They used to
    be copied onto the source, which no longer has them.)
    """

    class Fit:
        """Enough of a pyLIMA fit for set_parameter_boundaries to set its guess and boundaries"""
        class model:
            @staticmethod
            def model_type():
                return 'PSPL'

        def __init__(self):
            self.fit_parameters = {name: [0.0, [None, None]] for name in ('t0', 'u0', 'tE', 'rho')}

    def setUp(self):
        self.target, self.event, self.ndata, self.nlc, self.datums = create_test_target_with_photometry()

    def make_alert(self, t0, u0, tE, **kwargs):
        # Each alert has its own ID, as the database requires
        alert_id = RGESAlert.objects.count() + 1
        return RGESAlert.objects.create(
            alert_id=alert_id, roman_id='ROMAN-X', event=self.event, alert_t0=t0, alert_u0=u0, alert_tE=tE, **kwargs)

    def test_guess_and_boundaries_from_the_alert(self):
        self.make_alert(2460010.0, 0.25, 8.0)
        fit = self.Fit()

        pylima_fit_functions.set_parameter_boundaries(self.event, fit)

        self.assertEqual(fit.model_parameters_guess, [2460010.0, 0.25, 8.0])
        # t0 within twice the timescale of the alert's, centred on it
        self.assertEqual(fit.fit_parameters['t0'][1], [2460010.0 - 8.0, 2460010.0 + 8.0])
        self.assertEqual(fit.fit_parameters['tE'][1], [0.0, 100.0])
        self.assertEqual(fit.fit_parameters['u0'][1], [-2.0, 2.0])

    def test_the_most_recent_alert_is_used(self):
        older = self.make_alert(2460001.0, 0.1, 2.0)
        RGESAlert.objects.filter(pk=older.pk).update(created_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc))
        self.make_alert(2460020.0, 0.3, 3.0)

        self.assertEqual(pylima_fit_functions.get_alert_parameters(self.event), (2460020.0, 0.3, 3.0))

    def test_without_an_alert(self):
        fit = self.Fit()

        pylima_fit_functions.set_parameter_boundaries(self.event, fit)

        self.assertIsNone(pylima_fit_functions.get_alert_parameters(self.event))
        self.assertEqual(fit.model_parameters_guess, [0.0, 0.0, 0.0])
        self.assertEqual(fit.fit_parameters['t0'][1], [0.0, 10.0])

    def test_with_prior_model_parameters_they_are_the_guess(self):
        self.make_alert(2460010.0, 0.25, 8.0)
        fit = self.Fit()

        pylima_fit_functions.set_parameter_boundaries(
            self.event, fit, prior_model_params={'t0': 2460011.0, 'u0': 0.2, 'tE': 7.0})

        self.assertEqual(fit.model_parameters_guess, [2460011.0, 0.2, 7.0])

    def test_an_alert_without_a_timescale_still_gives_a_boundary(self):
        self.make_alert(2460010.0, None, None)
        fit = self.Fit()

        pylima_fit_functions.set_parameter_boundaries(self.event, fit)

        self.assertEqual(fit.model_parameters_guess, [2460010.0, 0.0, 0.0])
        self.assertEqual(fit.fit_parameters['t0'][1], [2460010.0 - 1.0, 2460010.0 + 1.0])


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

        test_tel = telescopes.Telescope(name='NONE',
                                        camera_filter='I',
                                        pixel_scale=1,
                                        lightcurve=np.zeros((1,3)),
                                        lightcurve_names=['time', 'mag', 'err_mag'],
                                        lightcurve_units=['JD', 'mag', 'err_mag'])

        model_fit = create_test_model_fit(test_event, pspl_model)

        model_params = pylima_fit_functions.gather_model_parameters(
            test_event, model_fit, True
        )

        model_tel = pylima_fit_functions.generate_model_lightcurve(
            test_event, model_params, True
        )

        assert(type(model_tel) is type(test_tel))
        assert(len(model_tel.lightcurve) >= len(test_event.telescopes[0].lightcurve))

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
        high_points = 10
        full_lightcurve = np.empty((self.ndata,3))
        full_lightcurve[:,0] = [Time(rd.timestamp).jd for rd in self.datums]
        full_lightcurve[0:high_points-1,1] = 16.0
        full_lightcurve[high_points:,1] = 20.0
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

        flux_model_lc = copy.deepcopy(lightcurve)
        nparam = 3  # Davenport flare model

        chisq, red_chisq, bic = flare_fit_functions.calc_goodness_of_flare_fit(
            lightcurve, flux_model_lc, nparam
        )

        test_bic = float(nparam) * np.log(len(lightcurve))

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
        self.assertFalse(np.isinf(log_prior))

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

class TestEventThumbnailIsNotALink(TestCase):
    """
    A thumbnail is only a picture. As a link to the file it was followed by the table's hx-boost,
    which put the picture's bytes into the page.
    """

    def setUp(self):
        self.client.force_login(User.objects.create_user('thumb_user'))
        target = Target.objects.create(name='ThumbLinkTarget', ra=10.0, dec=10.0)
        self.event = Event.objects.create(
            target=target, event_id='ThumbLink_1', start_time=2460000.0, duration=2.0,
            thumbnail='event_thumbnails/2026/10/11/ThumbLink_1_lc.png')

    def test_events_table_thumbnail(self):
        response = self.client.get(reverse('events:list'), headers={'HX-Request': 'true'})
        html = response.content.decode()

        self.assertIn('<img src="%s"' % self.event.thumbnail.url, html)
        # Not inside a link, nor linked to the file anywhere
        self.assertNotRegex(html, r'<a\b[^>]*>\s*<img')
        self.assertNotIn('href="%s"' % self.event.thumbnail.url, html)
        self.assertEqual([c.verbose_name for c in response.context['table'].columns][:2],
                         ['Target', 'Thumbnail'])

    def test_only_sortable_headers_are_marked_orderable(self):
        # custom.css takes the sort arrows off a header that isn't, so the thumbnail's mustn't be
        html = self.client.get(reverse('events:list'), headers={'HX-Request': 'true'}).content.decode()

        thumbnail = re.search(r'<th\b([^>]*)>\s*Thumbnail\s*</th>', html).group(1)
        event_id = re.search(r'<th\b([^>]*)>\s*Event id\s*</th>', html).group(1)

        self.assertNotIn('orderable', thumbnail)
        self.assertIn('orderable', event_id)

    def test_events_table_without_a_thumbnail(self):
        Event.objects.filter(pk=self.event.pk).update(thumbnail='')

        response = self.client.get(reverse('events:list'), headers={'HX-Request': 'true'})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('lightcurve thumbnail', response.content.decode())


@override_settings(TOM_MFA_REQUIRED=None)
class TestEventAlertsPanel(TestCase):
    """The alert parameters on the event page are styled as the event and model parameters are"""

    def setUp(self):
        self.client.force_login(User.objects.create_user('alerts_user'))
        target = Target.objects.create(name='AlertsPanelTarget', ra=10.0, dec=10.0)
        self.event = Event.objects.create(target=target, event_id='EVP_1', start_time=2460000.0, duration=2.0)

    def get_panel(self):
        response = self.client.get(reverse('events:alerts'), {'event': self.event.pk},
                                   headers={'HX-Request': 'true'})
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_one_group_of_values_per_alert(self):
        for alert_id, origin in ((1, 'MSOS'), (2, 'Aethra')):
            RGESAlert.objects.create(alert_id=alert_id, roman_id='ROMAN-EVP_1', event=self.event,
                                     alert_origin=origin, alert_t0=2460001.5, alert_tE=12.0)
        html = self.get_panel()

        self.assertIn('event-params-panel', html)
        self.assertEqual(html.count('event-params-group"'), 2)
        self.assertIn('MSOS alert parameters', html)
        self.assertIn('Aethra alert parameters', html)
        self.assertIn('2460001.50000', html)
        self.assertNotIn('<table', html)

    def test_no_alerts(self):
        html = self.get_panel()

        self.assertIn('No alerts for this event yet', html)
        self.assertNotIn('<table', html)


@override_settings(TOM_MFA_REQUIRED=None)
class TestGeneralSearch(TestCase):
    """The general search box on the Events and Alerts pages"""

    def setUp(self):
        self.client.force_login(User.objects.create_user('search_user'))
        self.target_a = Target.objects.create(name='SearchTargetA', ra=10.0, dec=10.0)
        self.target_b = Target.objects.create(name='SearchTargetB', ra=20.0, dec=10.0)
        self.event_a = Event.objects.create(
            target=self.target_a, event_id='EVA_24', start_time=2460000.0, duration=2.0)
        self.event_b = Event.objects.create(
            target=self.target_b, event_id='EVB_99', start_time=2460010.0, duration=2.0,
            nearest_moving_object='Ceres')
        PSPLModel.objects.create(event=self.event_a, model_type='PSPL microlensing', chisq=24.0)
        for event in (self.event_a, self.event_b):
            RGESAlert.objects.create(
                alert_id=1, roman_id='ROMAN-' + event.event_id, event=event, alert_origin='MSOS')

    def test_migration_sets_target_of_existing_alerts(self):
        migration = importlib.import_module('custom_code.migrations.0042_rgesalert_target')
        RGESAlert.objects.update(target=None)
        orphan = RGESAlert.objects.create(alert_id=3, roman_id='ROMAN-Y')

        migration.set_target_from_event(django_apps, None)

        self.assertEqual(RGESAlert.objects.get(event=self.event_a).target, self.target_a)
        self.assertEqual(RGESAlert.objects.get(event=self.event_b).target, self.target_b)
        orphan.refresh_from_db()
        self.assertIsNone(orphan.target)

    def test_alert_takes_its_events_target(self):
        alert = RGESAlert.objects.get(event=self.event_a)
        self.assertEqual(alert.target, self.target_a)
        self.assertEqual(list(self.target_b.alerts.values_list('roman_id', flat=True)), ['ROMAN-EVB_99'])

        # ...unless it's given one, and an alert needs no event
        other = RGESAlert.objects.create(alert_id=2, roman_id='ROMAN-X', event=self.event_a, target=self.target_b)
        self.assertEqual(other.target, self.target_b)
        self.assertIsNone(RGESAlert.objects.create(alert_id=3, roman_id='ROMAN-Y').target)

    def found(self, url_name, query):
        response = self.client.get(reverse(url_name), {'query': query}, headers={'HX-Request': 'true'})
        self.assertEqual(response.status_code, 200)
        return response

    def test_event_search(self):
        for query, expected, unexpected in [
            ('EVA', 'EVA_24', 'EVB_99'),             # event ID
            ('TargetB', 'EVB_99', 'EVA_24'),         # source name
            ('ceres', 'EVB_99', 'EVA_24'),           # nearest moving object, case-insensitive
        ]:
            with self.subTest(query=query):
                response = self.found('events:list', query)
                self.assertContains(response, expected)
                self.assertNotContains(response, unexpected)

        # Any field of the event: a number is found wherever it occurs
        Event.objects.filter(pk=self.event_b.pk).update(delta_chi2_PSPL=777.5, Nlinked_events=3)
        response = self.found('events:list', '777.5')
        self.assertContains(response, 'EVB_99')
        self.assertNotContains(response, 'EVA_24')
        self.assertContains(self.found('events:list', 'EVA_24'), 'EVA_24')

    def test_event_table_scrolls_horizontally(self):
        # More than a page of events, so that there is a pagination bar
        for i in range(25):
            Event.objects.create(target=self.target_a, event_id=f'EVX_{i}', start_time=2460100.0 + i, duration=1.0)

        # The full page, and the fragments HTMX swaps in for a sort or a change of page
        for params, headers in [({}, {}), ({'sort': 'duration'}, {'HX-Request': 'true'}),
                                ({'page': 2}, {'HX-Request': 'true'})]:
            with self.subTest(params=params):
                html = self.client.get(reverse('events:list'), params, headers=headers).content.decode()
                self.assertEqual(html.count('class="table-responsive"'), 1)
                # Only the table is in the scroller: the pagination bar follows it
                self.assertRegex(html, r'(?s)class="table-responsive".*?</table>\s*</div>\s*<nav')

    def test_event_model_search(self):
        for query, expected in [('TargetA', 'SearchTargetA'), ('pspl', 'PSPL microlensing')]:
            with self.subTest(query=query):
                self.assertContains(self.found('eventmodels:list', query), expected)
        self.assertNotContains(self.found('eventmodels:list', 'TargetB'), 'SearchTargetA')

    def test_alert_search(self):
        for query, expected, unexpected in [
            ('ROMAN-EVA', 'ROMAN-EVA_24', 'ROMAN-EVB_99'),   # Roman ID
            ('TargetB', 'ROMAN-EVB_99', 'ROMAN-EVA_24'),     # source name
        ]:
            with self.subTest(query=query):
                response = self.found('candidates:list', query)
                self.assertContains(response, expected)
                self.assertNotContains(response, unexpected)


class TestTaskQueuing(TestCase):
    """
    The tasks that work out a target's or event's derived values are queued when it is created
    or the fields they depend on change, and not by every other save
    """

    def setUp(self):
        patches = {name: mock.patch(f'custom_code.signals.{name}') for name in
                   ('compute_source_diagnostics',
                    'check_event_for_moving_objects', 'make_event_lightcurve')}
        self.queued = {name: patch.start() for name, patch in patches.items()}
        for patch in patches.values():
            self.addCleanup(patch.stop)

    def counts(self):
        counts = {name: task.enqueue.call_count for name, task in self.queued.items()}
        for task in self.queued.values():
            task.enqueue.reset_mock()
        return counts

    def only(self, *names):
        return {name: int(name in names) for name in self.queued}

    def test_event_tasks(self):
        target = Target.objects.create(name='QueueTarget', ra=10.0, dec=10.0)
        self.counts()
        event_tasks = ('check_event_for_moving_objects', 'make_event_lightcurve')

        event = Event.objects.create(target=target, event_id='Q_1', start_time=2460000.0, duration=2.0)
        self.assertEqual(self.counts(), self.only(*event_tasks))

        # Saves that don't change when the event happens: whole or partial, repeated, or from
        # an instance holding stale values (as in the modeling code)
        stale = Event.objects.get(pk=event.pk)
        event.delta_chi2_PSPL = 3.0
        event.save()
        event.save()
        event.save(update_fields=['delta_chi2_PSPL'])
        Event.objects.filter(pk=event.pk).update(peak_mag=20.0)
        stale.save()
        self.assertEqual(self.counts(), self.only())

        # Changes to it, however they're saved
        event.duration = 3.0
        event.save()
        self.assertEqual(self.counts(), self.only(*event_tasks))
        event.start_time = 2460001.0
        event.save(update_fields=['start_time'])
        self.assertEqual(self.counts(), self.only(*event_tasks))

        # ...but only when it is a change: the new value is what's stored already
        event.save(update_fields=['start_time', 'duration'])
        self.assertEqual(self.counts(), self.only())

        # An instance with stale old values changes nothing if the stored row matches it
        stale.start_time, stale.duration = event.start_time, event.duration
        stale.save()
        self.assertEqual(self.counts(), self.only())

    def test_target_tasks(self):
        target_tasks = ('compute_source_diagnostics',)

        target = Target.objects.create(name='QueueTarget', ra=10.0, dec=10.0)
        self.assertEqual(self.counts(), self.only(*target_tasks))

        target.distance = 2460000.5   # (any field that isn't its position)
        target.save()
        target.save(update_fields=['distance'])
        self.assertEqual(self.counts(), self.only())

        target.ra = 11.0
        target.save()
        self.assertEqual(self.counts(), self.only(*target_tasks))

        target.dec = 12.0
        target.save(update_fields=['dec'])
        self.assertEqual(self.counts(), self.only(*target_tasks))

        # Edited through the TOM's own Target form: a full save with the position changed
        edited = Target.objects.get(pk=target.pk)
        edited.ra = 13.0
        edited.save()
        self.assertEqual(self.counts(), self.only(*target_tasks))


class TestEventThumbnailSurvivesModeling(TestCase):
    """
    The thumbnail is made by a background task while the process that ingested the alert goes on
    modeling the event, with the Event instance it loaded before the thumbnail existed. The
    diagnostics that save that instance must write only what they calculated: a full save writes the
    old, empty thumbnail back over the new one.
    """

    THUMBNAIL = 'event_thumbnails/2026/10/11/made_by_the_task.png'

    def setUp(self):
        target = Target.objects.create(name='ThumbTarget', ra=10.0, dec=10.0)
        self.event = Event.objects.create(target=target, event_id='THUMB_1', start_time=2460000.0, duration=2.0)
        # The task finishes while the ingest still holds its own copy, which has no thumbnail
        Event.objects.filter(pk=self.event.pk).update(thumbnail=self.THUMBNAIL)
        self.assertFalse(self.event.thumbnail)

    def assertThumbnailKept(self, **expected):
        stored = Event.objects.get(pk=self.event.pk)
        self.assertEqual(stored.thumbnail.name, self.THUMBNAIL)
        for name, value in expected.items():
            self.assertAlmostEqual(getattr(stored, name), value, msg=name)

    def test_straight_line_comparisons(self):
        straight_line = StraightLineModel(model_type='Straight line', chisq=100.0, BIC=110.0)
        cases = [
            (PSPLModel(model_type='PSPL microlensing', chisq=40.0, BIC=45.0),
             dict(delta_chi2_PSPL=-60.0, delta_BIC_PSPL=-65.0)),
            (FSPLModel(model_type='FSPL microlensing', chisq=30.0, BIC=35.0),
             dict(delta_chi2_FSPL=-70.0, delta_BIC_FSPL=-75.0)),
        ]
        for mulens, expected in cases:
            with self.subTest(model=mulens.model_type):
                diagnostics.compare_mulens_with_straightline(self.event, mulens, straight_line)
                self.assertThumbnailKept(**expected)

    def test_flare_model_comparisons(self):
        pspl = PSPLModel(model_type='PSPL microlensing', chisq=40.0, BIC=45.0)
        fspl = FSPLModel(model_type='FSPL microlensing', chisq=30.0, BIC=35.0)
        # The better flare model, by reduced chisq, is the one the microlensing models are compared with
        davenport = DavenportFlareModel(model_type='Davenport flare', chisq=60.0, BIC=70.0, red_chisq=1.1)
        pitkin = PitkinFlareModel(model_type='Pitkin flare', chisq=80.0, BIC=90.0, red_chisq=1.9)

        diagnostics.compare_flare_models(self.event, pspl, fspl, davenport, pitkin)

        self.assertThumbnailKept(
            delta_chi2_PSPL_bestflare=-20.0, delta_BIC_PSPL_bestflare=-25.0,
            delta_chi2_FSPL_bestflare=-30.0, delta_BIC_FSPL_bestflare=-35.0,
        )
        self.assertEqual(Event.objects.get(pk=self.event.pk).bestflare_model_type.strip(), 'Davenport')

    def test_best_flare_model_is_the_lower_reduced_chisq(self):
        pspl = PSPLModel(model_type='PSPL microlensing', chisq=40.0, BIC=45.0)
        fspl = FSPLModel(model_type='FSPL microlensing', chisq=30.0, BIC=35.0)
        davenport = DavenportFlareModel(model_type='Davenport flare', chisq=60.0, BIC=70.0, red_chisq=2.5)
        pitkin = PitkinFlareModel(model_type='Pitkin flare', chisq=80.0, BIC=90.0, red_chisq=1.5)

        diagnostics.compare_flare_models(self.event, pspl, fspl, davenport, pitkin)

        self.assertThumbnailKept(delta_chi2_PSPL_bestflare=-40.0, delta_BIC_PSPL_bestflare=-45.0)
        self.assertEqual(Event.objects.get(pk=self.event.pk).bestflare_model_type.strip(), 'Pitkin')

    def test_microlensing_diagnostics(self):
        pspl = PSPLModel(model_type='PSPL microlensing', chisq=40.0, BIC=45.0, red_chisq=1.4)
        fspl = FSPLModel(model_type='FSPL microlensing', chisq=30.0, BIC=35.0, red_chisq=1.2)
        straight_line = StraightLineModel(model_type='Straight line', chisq=100.0, BIC=110.0)

        diagnostics.calc_mulens_diagnostics(self.event, pspl, fspl, straight_line)

        self.assertThumbnailKept(
            delta_chi2_PSPL=-60.0, delta_BIC_PSPL=-65.0, delta_chi2_FSPL=-70.0, delta_BIC_FSPL=-75.0,
        )
        self.assertEqual(Event.objects.get(pk=self.event.pk).bestmulens_model_type.strip(), 'FSPL')

    def test_baseline_diagnostics(self):
        data_utils.store_baseline_diagnostics(self.event, {
            'frac_below_baseline': 0.4, 'max_excursion_below_baseline': -0.3, 'Npoint_above_3sigma': 7,
        })
        self.assertThumbnailKept(frac_below_baseline=0.4, max_excursion_below_baseline=-0.3, Npoint_above_3sigma=7)


class TestIngestAlertsWorkers(TestCase):
    """
    The workers of ingest_alerts are new interpreters (macOS starts them by "spawn"). Each imports the
    command's module to find the function it is to run before its initializer sets Django up, so that
    module mustn't import models at the top.
    """

    MODULE = 'custom_code.management.commands.ingest_alerts'

    def test_module_imports_before_django_is_set_up(self):
        result = subprocess.run(
            [sys.executable, '-c', 'import ' + self.MODULE],
            capture_output=True, text=True, env=os.environ, cwd=os.getcwd(),
        )

        self.assertEqual(result.returncode, 0, result.stderr[-1500:])

    def test_spawned_worker_runs_the_ingest_function(self):
        from custom_code.management.commands import ingest_alerts

        # A file that isn't there: the worker gets as far as opening it, past the imports of
        # models, and says so, rather than dying as the pool does when its workers can't start.
        # Nothing is ingested, so the database isn't touched.
        with ProcessPoolExecutor(
            max_workers=1, mp_context=multiprocessing.get_context('spawn'),
            initializer=ingest_alerts._init_worker,
        ) as executor:
            future = executor.submit(ingest_alerts.ingest_alert_and_model_event, '/nowhere/alert.json')

            with self.assertRaises(FileNotFoundError):
                future.result(timeout=120)


class TestMcmcChains(TestCase):
    """The MCMC samples of a model are saved as a .npy file, and the corner plot is made from them"""

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings_override = override_settings(MEDIA_ROOT=self.media.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        self.target = Target.objects.create(name='ChainsTarget', ra=10.0, dec=10.0)
        self.event = Event.objects.create(
            target=self.target, event_id='ChainsTarget_1', start_time=2460000.0, duration=2.0)
        self.model = PSPLModel.objects.create(event=self.event, model_type='PSPL microlensing')
        self.samples = np.random.default_rng(3).normal(size=(500, 5))

    def results(self):
        return {'samples': self.samples, 'sample_columns': [0, 1, 2], 'parameter_labels': ['t0', 'u0', 'tE']}

    def stored(self):
        return EventModel.objects.get(pk=self.model.pk)

    def files(self, directory):
        return [path for path in storage_walk(default_storage, directory)]

    def test_array_round_trips_through_the_storage(self):
        utils.store_array_as_np(self.samples, 'chains_test.npy', self.model.mcmc_chains)
        self.model.save()

        stored = self.stored()
        loaded = utils.load_array_from_file(stored.mcmc_chains)

        self.assertRegex(stored.mcmc_chains.name, r'^arrays/\d{4}/\d{2}/\d{2}/chains_test\.npy$')
        self.assertTrue(np.array_equal(loaded, self.samples))
        self.assertEqual(loaded.dtype, self.samples.dtype)

    def test_corner_plot_and_chains_are_stored(self):
        data_utils.generate_corner_plot(self.model, self.results(), 'ChainsTarget_1_PSPL_corner_plot.png')

        stored = self.stored()
        self.assertTrue(stored.corner_plot.name.endswith('/ChainsTarget_1_PSPL_corner_plot.png'))
        self.assertTrue(stored.mcmc_chains.name.endswith('/ChainsTarget_1_PSPL_mcmc_chains.npy'))
        self.assertTrue(np.array_equal(utils.load_array_from_file(stored.mcmc_chains), self.samples))

    def test_recalculating_replaces_the_files(self):
        data_utils.generate_corner_plot(self.model, self.results(), 'ChainsTarget_1_PSPL_corner_plot.png')
        self.samples = self.samples * 2.0
        data_utils.generate_corner_plot(self.model, self.results(), 'ChainsTarget_1_PSPL_corner_plot.png')

        self.assertEqual(len(self.files('arrays')), 1)
        self.assertEqual(len(self.files('eventmodel_plots')), 1)
        self.assertTrue(np.array_equal(utils.load_array_from_file(self.stored().mcmc_chains), self.samples))

    def test_the_chains_file_is_named_from_the_plot_name_without_its_extension(self):
        data_utils.generate_corner_plot(self.model, self.results(), 'ChainsTarget_1_other.png')

        name = self.stored().mcmc_chains.name
        self.assertTrue(name.endswith('/ChainsTarget_1_other_mcmc_chains.npy'), name)

    def test_a_failed_fit_removes_the_files_and_what_refers_to_them(self):
        data_utils.generate_corner_plot(self.model, self.results(), 'ChainsTarget_1_PSPL_corner_plot.png')
        self.assertEqual(len(self.files('arrays')), 1)

        data_utils.generate_corner_plot(self.model, {}, 'ChainsTarget_1_PSPL_corner_plot.png')

        stored = self.stored()
        self.assertFalse(stored.corner_plot)
        self.assertFalse(stored.mcmc_chains)
        self.assertEqual(self.files('arrays'), [])
        self.assertEqual(self.files('eventmodel_plots'), [])

    def test_remove_source_removes_the_chains(self):
        from custom_code.management.commands.remove_source import walk as storage_walk_command
        data_utils.generate_corner_plot(self.model, self.results(), 'ChainsTarget_1_PSPL_corner_plot.png')
        other = Target.objects.create(name='KeepChains', ra=20.0, dec=10.0)
        kept = default_storage.save('arrays/2026/10/11/KeepChains_1_PSPL_mcmc_chains.npy', ContentFile(b'npy'))
        left_behind = default_storage.save('arrays/2026/10/08/ChainsTarget_1_PSPL_mcmc_chains.npy', ContentFile(b'npy'))

        call_command('remove_source', 'ChainsTarget', stdout=StringIO())

        self.assertEqual(self.files('arrays'), [kept])
        self.assertFalse(default_storage.exists(left_behind))
        self.assertTrue(Target.objects.filter(pk=other.pk).exists())


def storage_walk(storage, directory):
    from custom_code.management.commands.remove_source import walk
    return list(walk(storage, directory))


class TestMcmcChainsDownload(TestCase):
    """The model's parameters offer its MCMC chains for download, if it has them"""

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings_override = override_settings(MEDIA_ROOT=self.media.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        self.client.force_login(User.objects.create_user('chains_user'))
        target = Target.objects.create(name='DownloadTarget', ra=10.0, dec=10.0)
        event = Event.objects.create(target=target, event_id='DownloadTarget_1', start_time=2460000.0, duration=2.0)
        self.model = PSPLModel.objects.create(event=event, model_type='PSPL microlensing', t0=2460001.0, tE=3.0)
        self.samples = np.random.default_rng(4).normal(size=(300, 6))

    def with_chains(self):
        utils.store_array_as_np(self.samples, 'DownloadTarget_1_PSPL_mcmc_chains.npy', self.model.mcmc_chains)
        EventModel.objects.filter(pk=self.model.pk).update(mcmc_chains=self.model.mcmc_chains.name)

    def parameters_page(self):
        response = self.client.get(reverse('eventmodels:parameters'), {'model': self.model.pk},
                                   headers={'HX-Request': 'true'})
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def url(self):
        return reverse('eventmodels:mcmc-chains', kwargs={'pk': self.model.pk})

    def test_button_is_shown_if_the_model_has_chains(self):
        self.with_chains()

        html = self.parameters_page()

        self.assertIn('href="%s"' % self.url(), html)
        self.assertIn('Download MCMC chains', html)

    def test_no_button_without_chains(self):
        html = self.parameters_page()

        self.assertNotIn('Download MCMC chains', html)
        self.assertNotIn('mcmc-chains', html)

    def test_the_file_is_downloaded(self):
        self.with_chains()

        response = self.client.get(self.url())
        content = b''.join(response.streaming_content)

        self.assertEqual(response.status_code, 200)
        disposition = response['Content-Disposition']
        self.assertTrue(disposition.startswith('attachment;'), disposition)
        self.assertIn('DownloadTarget_1_PSPL_mcmc_chains.npy', disposition)
        self.assertTrue(np.array_equal(np.load(io.BytesIO(content), allow_pickle=False), self.samples))

    def test_a_model_without_chains_has_nothing_to_download(self):
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_a_file_that_is_missing_from_the_storage(self):
        self.with_chains()
        default_storage.delete(EventModel.objects.get(pk=self.model.pk).mcmc_chains.name)

        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_a_model_that_is_not_there(self):
        self.assertEqual(self.client.get(reverse('eventmodels:mcmc-chains', kwargs={'pk': 999999})).status_code, 404)

    def test_login_is_required(self):
        self.with_chains()
        self.client.logout()

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/accounts/login/'))


class TestRemoveSource(TestCase):
    """The remove_source command removes a source's image files with the source"""

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings_override = override_settings(MEDIA_ROOT=self.media.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        self.target = Target.objects.create(name='RemoveMe', ra=10.0, dec=10.0)
        self.event = Event.objects.create(target=self.target, event_id='RemoveMe_1', start_time=2460000.0, duration=2.0)
        self.other = Target.objects.create(name='KeepMe', ra=20.0, dec=10.0)
        self.other_event = Event.objects.create(target=self.other, event_id='KeepMe_1', start_time=2460000.0, duration=2.0)

        # The source's thumbnails: the one its event uses, and those left by earlier ingests
        self.used = self.save_file('event_thumbnails/2026/10/11/RemoveMe_1_lc.png')
        self.leftover = [
            self.save_file('event_thumbnails/2026/10/10/RemoveMe_RemoveMe_1_lc.png'),
            self.save_file('event_thumbnails/2026/10/08/RemoveMe_1_lc_abCd123.png'),
            self.save_file('event_thumbnails/2026/09/18/RemoveMe_8004_lc.png'),   # from an event ID since replaced
        ]
        # Others', and similar names that aren't this source's thumbnails
        self.kept = [
            self.save_file('event_thumbnails/2026/10/11/KeepMe_1_lc.png'),
            self.save_file('event_thumbnails/2026/10/11/RemoveMe2_RemoveMe2_1_lc.png'),     # another source, named alike
            self.save_file('event_thumbnails/2026/10/11/RemoveMe_notes.txt'),
            self.save_file('event_thumbnails/2026/10/11/RemoveMe_9_lc.jpg'),
        ]
        Event.objects.filter(pk=self.event.pk).update(thumbnail=self.used)
        Event.objects.filter(pk=self.other_event.pk).update(thumbnail=self.kept[0])

        # The corner plots of its models, likewise
        self.used_plot = self.save_file('eventmodel_plots/2026/10/11/RemoveMe_1_PSPL_corner_plot.png')
        self.leftover_plots = [
            self.save_file('eventmodel_plots/2026/10/10/RemoveMe_1_PSPL_corner_plot_Xy12abc.png'),
            self.save_file('eventmodel_plots/2026/09/18/RemoveMe_8004_davenport_corner_plot.png'),
        ]
        self.kept_plots = [
            self.save_file('eventmodel_plots/2026/10/11/KeepMe_1_PSPL_corner_plot.png'),
            self.save_file('eventmodel_plots/2026/10/11/RemoveMe2_1_PSPL_corner_plot.png'),
            self.save_file('eventmodel_plots/2026/10/11/RemoveMe_1_lc.png'),   # not a corner plot
        ]
        self.model = PSPLModel.objects.create(
            event=self.event, model_type='PSPL microlensing', corner_plot=self.used_plot)
        self.other_model = PSPLModel.objects.create(
            event=self.other_event, model_type='PSPL microlensing', corner_plot=self.kept_plots[0])

        # And its periodogram: the picture the source refers to, and one left from before
        self.used_periodogram = self.save_file('periodograms/2026/10/11/RemoveMe_periodogram.png')
        self.leftover_periodograms = [self.save_file('periodograms/2026/10/08/RemoveMe_periodogram_Zq8xK1m.png')]
        self.kept_periodograms = [
            self.save_file('periodograms/2026/10/11/KeepMe_periodogram.png'),
            self.save_file('periodograms/2026/10/11/RemoveMe2_periodogram.png'),   # another source, named alike
            self.save_file('periodograms/2026/10/11/RemoveMe_periodogram.txt'),
        ]
        Target.objects.filter(pk=self.target.pk).update(periodogram=self.used_periodogram)
        Target.objects.filter(pk=self.other.pk).update(periodogram=self.kept_periodograms[0])

        self.removed = ([self.used] + self.leftover + [self.used_plot] + self.leftover_plots
                        + [self.used_periodogram] + self.leftover_periodograms)
        self.not_removed = self.kept + self.kept_plots + self.kept_periodograms

    def save_file(self, name):
        return default_storage.save(name, ContentFile(b'png'))

    def exists(self, names):
        return [default_storage.exists(name) for name in names]

    def run_command(self, *args):
        out = StringIO()
        call_command('remove_source', 'RemoveMe', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_removes_nothing(self):
        output = self.run_command('--dry-run')

        self.assertIn('4 thumbnail files (1 used by rows, 3 left by earlier ingests)', output)
        self.assertIn('3 corner plot files (1 used by rows, 2 left by earlier ingests)', output)
        self.assertIn('2 periodogram files (1 used by rows, 1 left by earlier ingests)', output)
        for name in self.removed:
            self.assertIn('would remove ' + name, output)
        self.assertNotIn('KeepMe', output)
        self.assertEqual(self.exists(self.removed + self.not_removed), [True] * (len(self.removed) + len(self.not_removed)))
        self.assertTrue(Target.objects.filter(name='RemoveMe').exists())
        self.assertTrue(PSPLModel.objects.filter(pk=self.model.pk).exists())

    def test_removes_the_source_and_its_images(self):
        output = self.run_command()

        self.assertIn('4 thumbnail files', output)
        self.assertIn('3 corner plot files', output)
        self.assertIn('2 periodogram files', output)
        self.assertEqual(self.exists(self.removed), [False] * len(self.removed))
        self.assertFalse(Target.objects.filter(name='RemoveMe').exists())
        self.assertFalse(Event.objects.filter(pk=self.event.pk).exists())
        self.assertFalse(PSPLModel.objects.filter(pk=self.model.pk).exists())

        # Nothing of any other source, nor the files that only look similar
        self.assertEqual(self.exists(self.not_removed), [True] * len(self.not_removed))
        self.assertTrue(Event.objects.filter(pk=self.other_event.pk).exists())
        self.assertTrue(PSPLModel.objects.filter(pk=self.other_model.pk).exists())

    def test_a_source_without_images(self):
        Event.objects.filter(pk=self.event.pk).update(thumbnail=None)
        EventModel.objects.filter(pk=self.model.pk).update(corner_plot=None)
        Target.objects.filter(pk=self.target.pk).update(periodogram=None)
        for name in self.removed:
            default_storage.delete(name)

        output = self.run_command()

        self.assertIn('0 thumbnail files', output)
        self.assertIn('0 corner plot files', output)
        self.assertIn('0 periodogram files', output)
        self.assertFalse(Target.objects.filter(name='RemoveMe').exists())

    def test_unknown_source(self):
        with self.assertRaises(CommandError):
            call_command('remove_source', 'NoSuchSource', stdout=StringIO())


class TestEventThumbnailName(TestCase):
    """The lightcurve thumbnail's name has the source's name once"""

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings_override = override_settings(MEDIA_ROOT=self.media.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

    def make_event(self, source_name, event_id):
        target = Target.objects.create(name=source_name, ra=10.0, dec=10.0)
        event = Event.objects.create(target=target, event_id=event_id, start_time=2461000.0, duration=1.0)
        # The thumbnail is of the F146 lightcurve during the event
        PhotometryReducedDatum.objects.bulk_create([PhotometryReducedDatum(
            target=target, source_name='Roman_F146', bandpass='F146', brightness=20.0 + 0.01 * i,
            brightness_error=0.01,
            timestamp=timezone.make_aware(Time(2461000.0 + i * 0.05, format='jd').datetime, datetime.timezone.utc),
        ) for i in range(10)])
        return event

    def test_event_file_stem(self):
        for source, event_id, expected in [
            ('RMDC26_072622', 'RMDC26_072622_72622', 'RMDC26_072622_72622'),   # IDs of events made from alerts
            ('RMDC26_072622', '8004', 'RMDC26_072622_8004'),                   # plain IDs
            ('RMDC26_072622', 8004, 'RMDC26_072622_8004'),
            ('Src', 'Src', 'Src_Src'),
            ('Src', 'SrcOther_1', 'Src_SrcOther_1'),                           # only a whole name before the _ counts
        ]:
            with self.subTest(source=source, event_id=event_id):
                event = Event(target=Target(name=source), event_id=event_id)
                self.assertEqual(event_functions.event_file_stem(event), expected)

    def test_thumbnail_name(self):
        for source, event_id, expected in [
            ('RMDC26_072622', 'RMDC26_072622_72622', 'RMDC26_072622_72622_lc.png'),
            ('RMDC26_070222', '1840', 'RMDC26_070222_1840_lc.png'),
        ]:
            with self.subTest(event_id=event_id):
                event = self.make_event(source, event_id)

                event_functions.generate_event_lightcurves(event)

                stored = Event.objects.get(pk=event.pk).thumbnail.name
                self.assertEqual(posixpath.basename(stored), expected)
                self.assertTrue(default_storage.exists(stored))


class TestCornerPlotNames(TestCase):
    """The corner plots' names have the source's name once, whichever way the fits are run"""

    CASES = [
        ('RMDC26_072622', 'RMDC26_072622_72622', 'RMDC26_072622_72622'),   # IDs of events made from alerts
        ('RMDC26_070222', '1840', 'RMDC26_070222_1840'),
    ]

    def make_event(self, source_name, event_id):
        target = Target.objects.create(name=source_name, ra=10.0, dec=10.0)
        return Event.objects.create(target=target, event_id=event_id, start_time=2461000.0, duration=1.0)

    def names_made(self, corner_plot_mock):
        return [call.args[2] for call in corner_plot_mock.call_args_list]

    def test_event_modeling(self):
        for source, event_id, stem in self.CASES:
            with self.subTest(event_id=event_id):
                event = self.make_event(source, event_id)
                with mock.patch.multiple(
                        'custom_code.event_functions', data_utils=mock.DEFAULT, diagnostics=mock.DEFAULT,
                        general_fit_functions=mock.DEFAULT, pylima_fit_functions=mock.DEFAULT,
                        flare_fit_functions=mock.DEFAULT) as mocks:
                    mocks['data_utils'].store_microlensing_model_parameters.return_value = (mock.Mock(), mock.Mock())

                    event_functions.run_event_modeling(event)

                self.assertEqual(self.names_made(mocks['data_utils'].generate_corner_plot), [
                    stem + '_PSPL_corner_plot.png', stem + '_FSPL_corner_plot.png',
                    stem + '_davenport_corner_plot.png', stem + '_pitkin_corner_plot.png',
                ])

    def test_microlensing_command(self):
        for source, event_id, stem in self.CASES:
            with self.subTest(event_id=event_id):
                self.make_event(source, event_id)
                with mock.patch('custom_code.management.commands.fit_microlensing_model.data_utils') as data_utils_mock, \
                        mock.patch('custom_code.management.commands.fit_microlensing_model.pylima_fit_functions'):
                    data_utils_mock.store_microlensing_model_parameters.return_value = (mock.Mock(), mock.Mock())

                    call_command('fit_microlensing_model', source)

                self.assertEqual(self.names_made(data_utils_mock.generate_corner_plot),
                                 [stem + '_PSPL_corner_plot.png', stem + '_FSPL_corner_plot.png'])

    def test_flare_command(self):
        for source, event_id, stem in self.CASES:
            with self.subTest(event_id=event_id):
                self.make_event(source, event_id)
                with mock.patch('custom_code.management.commands.fit_flare_models.data_utils') as data_utils_mock, \
                        mock.patch('custom_code.management.commands.fit_flare_models.flare_fit_functions'):
                    call_command('fit_flare_models', source)

                self.assertEqual(self.names_made(data_utils_mock.generate_corner_plot),
                                 [stem + '_davenport_corner_plot.png', stem + '_pitkin_corner_plot.png'])


class TestPhotometryPlot(TestCase):
    """The lightcurve plot is built in bulk, and large lightcurves are drawn with WebGL"""

    def setUp(self):
        self.target = Target.objects.create(name='PlotTarget', ra=10.0, dec=10.0)

    def add_photometry(self, source_name, n, start_jd=2461000.0, step=0.01, mag=20.0):
        PhotometryReducedDatum.objects.bulk_create([PhotometryReducedDatum(
            target=self.target, source_name=source_name, bandpass=source_name[-4:],
            brightness=mag + i * 1e-3, brightness_error=0.01,
            timestamp=timezone.make_aware(
                Time(start_jd + i * step, format='jd').datetime, datetime.timezone.utc),
        ) for i in range(n)])

    def datasets_plotted(self):
        with mock.patch('custom_code.templatetags.plotting_functions.plot_interactive_lightcurve') as plot:
            plotting_functions.photometry_mulens_model(self.target)
        return plot.call_args.args[0]

    def trace_types(self, make_plot):
        """The types of the traces in the figure a call builds. (Not looked for in the HTML, which
        includes Plotly's theme, with every type of trace in it.)"""
        with mock.patch('custom_code.templatetags.plotting_functions.offline.plot') as plot:
            make_plot()
        return [trace.type for trace in plot.call_args.args[0].data]

    @staticmethod
    def lightcurve(n):
        return {'Roman_F146': {'x': np.arange(n, dtype=float), 'y': np.full(n, 20.0), 'error': np.full(n, 0.01)}}

    def test_datasets_by_source(self):
        self.add_photometry('Roman_F146', 30)
        self.add_photometry('Roman_F087', 10, mag=21.0)

        datasets = self.datasets_plotted()

        self.assertEqual(list(datasets), ['Roman_F087', 'Roman_F146'])
        f146 = datasets['Roman_F146']
        self.assertEqual((len(f146['x']), len(f146['y']), len(f146['error'])), (30, 30, 30))
        # JD - 2460000, as astropy gives it, to the precision the values are rounded to
        expected_jd = Time(2461000.0 + np.arange(30) * 0.01, format='jd').jd - 2460000.0
        np.testing.assert_allclose(f146['x'], expected_jd, atol=1e-5)
        np.testing.assert_allclose(f146['y'], 20.0 + np.arange(30) * 1e-3, atol=1e-4)
        np.testing.assert_allclose(f146['error'], 0.01)
        self.assertAlmostEqual(datasets['Roman_F087']['y'][0], 21.0, 4)

    def test_no_photometry(self):
        self.assertEqual(self.datasets_plotted(), {})
        self.assertEqual(self.trace_types(lambda: plotting_functions.photometry_mulens_model(self.target)), [])

    def test_large_lightcurves_use_webgl(self):
        no_models = ReducedDatum.objects.none()
        big = self.lightcurve(plotting_functions.WEBGL_MIN_POINTS + 1)
        small = self.lightcurve(100)
        plot = plotting_functions.plot_interactive_lightcurve

        self.assertEqual(self.trace_types(lambda: plot(big, no_models)), ['scattergl'])
        self.assertEqual(self.trace_types(lambda: plot(small, no_models)), ['scatter'])
        # The points of all the bands are counted, and all are drawn the same way
        self.assertEqual(self.trace_types(lambda: plot({**small, 'Roman_F087': big['Roman_F146']}, no_models)),
                         ['scattergl', 'scattergl'])
        # Either way on request
        self.assertEqual(self.trace_types(lambda: plot(big, no_models, webgl=False)), ['scatter'])
        self.assertEqual(self.trace_types(lambda: plot(small, no_models, webgl=True)), ['scattergl'])

    def test_plot_of_a_large_lightcurve(self):
        self.add_photometry('Roman_F146', plotting_functions.WEBGL_MIN_POINTS + 10)

        types = self.trace_types(lambda: plotting_functions.photometry_mulens_model(self.target))

        self.assertEqual(types, ['scattergl'])

    def test_event_plots_stay_svg(self):
        self.add_photometry('Roman_F146', 50)
        event = Event.objects.create(target=self.target, event_id='PlotTarget_1', start_time=2461000.0, duration=0.4)

        types = self.trace_types(lambda: plotting_functions.photometry_event(event))

        self.assertEqual(types, ['scatter'])


@override_settings(TOM_MFA_REQUIRED=None)
class TestSourceDetailPageLoading(TestCase):
    """
    The source detail page must not wait on external hosts to be shown. A stylesheet or script
    in the page that comes from elsewhere holds up the first paint until it arrives, and the
    Aladin Lite host can take over ten seconds to answer.
    """

    def setUp(self):
        self.client.force_login(User.objects.create_superuser('detail_user', password='x'))
        self.target = Target.objects.create(name='DetailTarget', ra=10.0, dec=10.0, type='SIDEREAL')

    def get_page(self):
        response = self.client.get(reverse('targets:detail', kwargs={'pk': self.target.pk}))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_aladin_is_not_loaded_with_the_page(self):
        html = self.get_page()

        self.assertIsNone(re.search(r'<script[^>]+src="[^"]*aladin[^"]*"', html))
        self.assertIsNone(re.search(r'<link[^>]+href="[^"]*aladin[^"]*"', html))
        self.assertNotIn('aladin_finderchart.js"', re.sub(r'(?s)<script>.*?</script>', '', html))

    def test_imaging_tab_says_when_it_is_waiting_for_the_archive(self):
        html = self.get_page()

        box = re.search(r'<div id="archive-wait"[^>]*>(.*?)</div>\s*<span class="archive-wait-message">([^<]*)</span>', html, re.S)
        self.assertIsNotNone(box)
        self.assertEqual(box.group(2), 'Waiting for archive...')
        self.assertIn('spinner-border', box.group(1))
        # Hidden until the tab is shown, and inside the Imaging pane, above the chart. (Hidden with an
        # !important style as well as the attribute: the box is a d-flex, which the attribute doesn't beat.)
        opening = re.search(r'<div id="archive-wait"[^>]*>', html).group(0)
        self.assertRegex(opening, r'\shidden[\s>]')
        self.assertIn('display: none !important', opening)
        pane = html[html.index('id="imaging"'):]
        self.assertLess(pane.index('id="archive-wait"'), pane.index('id="aladin-lite-div"'))

        # Run by the shared script, when the tab is shown
        self.assertIn('static/tom_common/js/archive_wait.js', html)
        self.assertIn('ArchiveWait(box)', html)
        self.assertIn('wait.waiting();', html)

    def test_aladin_is_loaded_when_the_imaging_tab_is_shown(self):
        html = self.get_page()

        self.assertIn("addEventListener('shown.bs.tab', loadAladin)", html)
        self.assertIn('id="imaging-tab"', html)
        # The pane the chart goes in, for the toolkit's finder chart script to start in once loaded
        self.assertIn('id="aladin-lite-div"', html)
        self.assertIn('static/tom_targets/js/aladin_finderchart.js', html)


@override_settings(TOM_MFA_REQUIRED=None)
class TestSkymapWaitingBox(TestCase):
    """The target list's skymap says when it's waiting for the archive, as the source's Imaging tab does"""

    def setUp(self):
        self.client.force_login(User.objects.create_superuser('list_user', password='x'))
        Target.objects.create(name='ListTarget', ra=268.0, dec=-29.0, type='SIDEREAL')

    def test_skymap_has_the_box(self):
        response = self.client.get(reverse('targets:list'))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        box = re.search(r'<div id="archive-wait"[^>]*>(.*?)</div>\s*<span class="archive-wait-message">([^<]*)</span>', html, re.S)
        self.assertIsNotNone(box)
        self.assertEqual(box.group(2), 'Waiting for archive...')
        self.assertIn('spinner-border', box.group(1))
        # Shown from the start, above the map, and run by the shared script
        self.assertNotRegex(re.search(r'<div id="archive-wait"[^>]*>', html).group(0), r'\shidden[\s>]')
        self.assertLess(html.index('id="archive-wait"'), html.index('id="aladin-lite-div"'))
        self.assertLess(html.index('static/tom_common/js/archive_wait.js'), html.index('ArchiveWait('))
        self.assertIn('wait.waiting();', html)
        self.assertIn('wait.loaded();', html)
        self.assertIn('wait.failed(', html)


class TestVersionedStatic(TestCase):
    """A static script's URL changes when the file does, so that a browser doesn't go on using an old one"""

    def render(self, template='{% load static_versions %}{% versioned_static "tom_common/js/archive_wait.js" %}'):
        return Template(template).render(Context({}))

    def test_url_has_the_time_the_file_was_changed(self):
        path = finders.find('tom_common/js/archive_wait.js')

        url = self.render()

        self.assertEqual(url, '/static/tom_common/js/archive_wait.js?v=%d' % os.path.getmtime(path))

    def test_url_changes_with_the_file(self):
        # A file of its own, in a static directory of its own: the project's files may not be
        # the tests' to change (they're not, in the Docker image)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'probe.js')
            with open(path, 'w') as f:
                f.write('// probe')
            with override_settings(STATICFILES_DIRS=[directory]):
                before = self.render('{% load static_versions %}{% versioned_static "probe.js" %}')
                original = os.stat(path)

                os.utime(path, (original.st_atime, original.st_mtime + 100))

                after = self.render('{% load static_versions %}{% versioned_static "probe.js" %}')

        self.assertTrue(before.startswith('/static/probe.js?v='))
        self.assertNotEqual(after, before)

    def test_a_file_that_is_not_there_has_no_version(self):
        self.assertEqual(self.render('{% load static_versions %}{% versioned_static "no/such/file.js" %}'),
                         '/static/no/such/file.js')

    def test_the_pages_that_use_the_script_ask_for_it_by_a_versioned_url(self):
        for name in ('templates/tom_targets/target_detail.html', 'templates/tom_targets/partials/aladin_skymap.html'):
            with open(name, encoding='utf-8') as template_file:
                template = template_file.read()
            with self.subTest(template=name):
                self.assertIn("{% versioned_static 'tom_common/js/archive_wait.js' %}", template)
                self.assertNotIn("{% static 'tom_common/js/archive_wait.js' %}", template)


class TestArchiveWaitScript(TestCase):
    """The script behind the boxes is served, and has what the pages call"""

    def test_script(self):
        path = finders.find('tom_common/js/archive_wait.js')
        self.assertIsNotNone(path)
        with open(path, encoding='utf-8') as script_file:
            script = script_file.read()

        for expected in ('window.ArchiveWait', 'waiting:', 'loaded:', 'failed:', 'Waiting for archive...',
                         'The archive is not responding', r'/\/Norder\d+\//'):
            self.assertIn(expected, script)

    def test_survey_images_are_looked_for_however_they_are_loaded(self):
        # Aladin Lite loads some pictures with fetch and some as an <img>, and which it uses can differ with
        # the browser, so there's the browser's own record of what it has loaded as well as a wrapper on fetch
        with open(finders.find('tom_common/js/archive_wait.js'), encoding='utf-8') as script_file:
            script = script_file.read()

        self.assertIn('window.fetch = wrapper', script)
        self.assertIn('new PerformanceObserver', script)
        self.assertIn("observer.observe({type: 'resource'})", script)
        # ...with what it saw written to the console, to say why the box is still there if it is
        self.assertIn('console.debug', script)
        self.assertIn('survey image arrived', script)

    def test_the_box_is_hidden_with_an_important_style(self):
        # The box is a Bootstrap d-flex (display:flex !important), which beats the hidden attribute, so
        # that alone left it on the page after the archive had answered. Only an !important of its own,
        # as an inline style has, hides it.
        with open(finders.find('tom_common/js/archive_wait.js'), encoding='utf-8') as script_file:
            script = script_file.read()

        self.assertIn("box.style.setProperty('display', 'none', 'important')", script)
        self.assertIn("box.style.removeProperty('display')", script)
        # ...and every hiding and showing of it goes through that, rather than the attribute alone
        self.assertEqual(len(re.findall(r'box\.hidden\s*=', script)), 1)


@override_settings(TOM_MFA_REQUIRED=None)
class TestTargetListFilters(TestCase):
    """The target list has one cone search, around a target, in its Advanced section"""

    def setUp(self):
        self.user = User.objects.create_superuser('filter_user', password='x')
        self.client.force_login(self.user)
        # A and B are 3.6" apart, C is far away
        for name, ra, dec in [('ConeA', 268.0, -29.0), ('ConeB', 268.001, -29.0), ('ConeC', 10.0, 10.0)]:
            Target.objects.create(name=name, ra=ra, dec=dec, type='SIDEREAL')

    def filters_form(self):
        """The form of the target list's filters, as the list view builds it"""
        request = RequestFactory().get('/targets/')
        request.user = self.user
        return RogueTargetFilterSet(None, queryset=Target.objects.all(), request=request).form

    def found(self, **params):
        response = self.client.get(reverse('targets:list'), params, headers={'HX-Request': 'true'})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        return [name for name in ('ConeA', 'ConeB', 'ConeC') if '>' + name + '<' in content]

    def test_general_search_covers_name_alias_and_coordinates(self):
        TargetName.objects.create(target=Target.objects.get(name='ConeC'), name='Bulge-Alias-7')

        self.assertEqual(self.found(query='ConeA'), ['ConeA'])
        self.assertEqual(self.found(query='Bulge-Alias'), ['ConeC'])
        # RA or Dec: the text typed is in the coordinate, as the table shows it
        self.assertEqual(self.found(query='268.001'), ['ConeB'])
        self.assertEqual(self.found(query='268'), ['ConeA', 'ConeB'])
        self.assertEqual(self.found(query='268.0'), ['ConeA', 'ConeB'])   # RA 268 has no ".0" in its text
        self.assertEqual(self.found(query='-29'), ['ConeA', 'ConeB'])
        self.assertEqual(self.found(query='10'), ['ConeC'])
        self.assertEqual(self.found(query='10.0'), ['ConeC'])
        self.assertEqual(self.found(query='10.1'), [])
        self.assertEqual(self.found(query='269'), [])

    def test_general_search_finds_the_digits_anywhere_in_name_or_coordinates(self):
        """267 is found in the name, in an RA or in a Dec, wherever in the number the digits are"""
        wanted = {
            'RaExactly267': (267.0, 10.0),
            'RaContains267': (258.2673467, 10.0),
            'DecContains267': (30.0, -30.45267),
            'Name267Here': (30.0, 10.0),
        }
        unwanted = {'NoDigitsHere': (266.8993392941, -29.37799376882)}
        for name, (ra, dec) in {**wanted, **unwanted}.items():
            Target.objects.create(name=name, ra=ra, dec=dec, type='SIDEREAL')

        response = self.client.get(reverse('targets:list'), {'query': '267'}, headers={'HX-Request': 'true'})
        content = response.content.decode()

        for name in wanted:
            self.assertIn('>' + name + '<', content, name)
        for name in unwanted:
            self.assertNotIn('>' + name + '<', content, name)

    def test_general_search_does_not_round_numbers(self):
        """267 is not in 266.8993392941 or -29.37799376882, though it is within a degree of them"""
        Target.objects.create(name='RMDC26_042811', ra=266.8993392941, dec=-29.37799376882, type='SIDEREAL')

        def search(query):
            response = self.client.get(reverse('targets:list'), {'query': query}, headers={'HX-Request': 'true'})
            return 'RMDC26_042811' in response.content.decode()

        self.assertFalse(search('267'))
        self.assertFalse(search('-29.4'))
        self.assertTrue(search('266.89'))
        self.assertTrue(search('-29.37'))
        self.assertTrue(search('042811'))

        self.assertEqual(self.found(query='nothing like it'), [])
        self.assertEqual(self.found(query=''), ['ConeA', 'ConeB', 'ConeC'])

    def test_the_filters_are_the_projects(self):
        response = self.client.get(reverse('targets:list'))

        self.assertIsInstance(response.context['filter'], RogueTargetFilterSet)

    def test_only_the_target_cone_search_is_in_the_form(self):
        html = self.client.get(reverse('targets:list')).content.decode()

        self.assertIn('name="target_cone_search"', html)
        self.assertNotIn('name="cone_search"', html)
        self.assertNotIn('RA, Dec, Radius', html)
        # Labelled as the cone search, there being no other
        self.assertRegex(html, r'(?s)<label[^>]*for="id_target_cone_search"[^>]*>\s*Cone Search\s*</label>')
        self.assertNotIn('Cone Search (Target)', html)
        # The rest of the Advanced section is as it was, but for the toolkit's type menu, of sidereal
        # or not, being the classification
        self.assertIn('Advanced', html)
        self.assertIn('name="classification"', html)
        self.assertNotIn('name="type"', html)
        self.assertIn('name="targetlist__name"', html)

    def test_cone_search_is_on_the_row_of_the_menus(self):
        html = self.client.get(reverse('targets:list')).content.decode()

        # In the rendered page: the type and group menus and the cone search, in the one row
        advanced = html[html.index('id="advancedFilters"'):]
        rows = re.findall(r'<div\s+class="row[^"]*"\s*>(.*?)(?=<div\s+class="row|$)', advanced, re.S)
        row = rows[0]
        names = re.findall(r'name="(classification|targetlist__name|target_cone_search)"', row)
        self.assertEqual(names, ['classification', 'targetlist__name', 'target_cone_search'])
        self.assertEqual(sum('target_cone_search' in other for other in rows), 1)

    def test_layout_of_the_row(self):
        layout = self.filters_form().helper.layout

        row = find_row_with(layout, 'classification')
        columns = {column.fields[0]: column.css_class for column in row.fields}
        self.assertEqual(list(columns), ['classification', 'targetlist__name', 'target_cone_search'])
        # The menus a quarter of the row each, and the cone search the half that's left of it: wider
        # than it was in a row of its own, which it took half of in a column that was a third
        self.assertIn('col-md-3', columns['classification'])
        self.assertIn('col-md-3', columns['targetlist__name'])
        self.assertIn('col-md-6', columns['target_cone_search'])
        self.assertIn('g-2', row.css_class)
        self.assertIsNone(find_row_with(layout, 'cone_search'))
        self.assertIsNone(find_row_with(layout, 'type'))

    def test_menus_are_labelled_briefly(self):
        # So that they stay on one line in their columns, and the row's inputs line up
        form = self.filters_form()

        self.assertEqual(form.fields['classification'].label, 'Type')
        self.assertEqual(form.fields['targetlist__name'].label, 'Group')
        self.assertEqual(form.fields['target_cone_search'].label, 'Cone Search')

    def make_diagnostics(self, name, classification, created=None):
        entry = SourceDiagnostics.objects.create(target=Target.objects.get(name=name), classification=classification)
        if created is not None:
            SourceDiagnostics.objects.filter(pk=entry.pk).update(created_at=created)
        return entry

    def test_the_type_menu_is_of_classifications(self):
        self.make_diagnostics('ConeA', 'Microlensing PSPL')
        self.make_diagnostics('ConeB', 'Flare')
        self.make_diagnostics('ConeC', 'Flare')
        self.make_diagnostics('ConeC', '')    # unclassified is not a choice

        form = self.filters_form()

        self.assertEqual(list(form.fields['classification'].choices),
                         [('', '---------'), ('Flare', 'Flare'), ('Microlensing PSPL', 'Microlensing PSPL')])
        # The menu on the page, with the choices as the options
        html = self.client.get(reverse('targets:list')).content.decode()
        menu = re.search(r'<select name="classification".*?</select>', html, re.S).group(0)
        self.assertEqual(re.findall(r'<option value="([^"]*)"', menu), ['', 'Flare', 'Microlensing PSPL'])

    def test_a_source_is_found_by_its_latest_classification(self):
        utc = datetime.timezone.utc
        # A was a flare, and has since been reclassified; B has always been
        self.make_diagnostics('ConeA', 'Flare', datetime.datetime(2025, 1, 1, tzinfo=utc))
        self.make_diagnostics('ConeA', 'Microlensing PSPL', datetime.datetime(2026, 1, 1, tzinfo=utc))
        self.make_diagnostics('ConeB', 'Flare', datetime.datetime(2025, 6, 1, tzinfo=utc))
        # C has no diagnostics at all

        self.assertEqual(self.found(classification='Flare'), ['ConeB'])
        self.assertEqual(self.found(classification='Microlensing PSPL'), ['ConeA'])
        self.assertEqual(self.found(), ['ConeA', 'ConeB', 'ConeC'])

    def test_of_two_entries_of_the_same_moment_the_last_made_is_the_latest(self):
        moment = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        self.make_diagnostics('ConeA', 'Flare', moment)
        self.make_diagnostics('ConeA', 'Microlensing PSPL', moment)

        self.assertEqual(self.found(classification='Microlensing PSPL'), ['ConeA'])
        self.assertEqual(self.found(classification='Flare'), [])

    def test_the_toolkits_type_filter_still_works_in_a_query_string(self):
        self.assertEqual(self.found(type='SIDEREAL'), ['ConeA', 'ConeB', 'ConeC'])
        self.assertEqual(self.found(type='NON_SIDEREAL'), [])

    def test_classification_with_a_cone_search(self):
        self.make_diagnostics('ConeA', 'Microlensing PSPL')
        self.make_diagnostics('ConeB', 'Flare')

        self.assertEqual(self.found(target_cone_search='ConeA, 0.01', classification='Flare'), ['ConeB'])
        self.assertEqual(self.found(target_cone_search='ConeA, 0.01', classification='Microlensing PSPL'), ['ConeA'])

    def test_cone_search_around_a_target(self):
        self.assertEqual(self.found(target_cone_search='ConeA, 0.01'), ['ConeA', 'ConeB'])
        self.assertEqual(self.found(target_cone_search='ConeA, 0.0001'), ['ConeA'])
        self.assertEqual(self.found(target_cone_search='ConeC, 1'), ['ConeC'])
        self.assertEqual(self.found(), ['ConeA', 'ConeB', 'ConeC'])

    def test_a_value_that_is_not_a_cone_search_finds_nothing(self):
        for value in ['NoSuchTarget, 1', 'ConeA', 'ConeA, abc', ',', 'ConeA, 1, 2']:
            with self.subTest(value=value):
                self.assertEqual(self.found(target_cone_search=value), [])

    def test_the_coordinate_cone_search_still_works_in_a_query_string(self):
        self.assertEqual(self.found(cone_search='268.0, -29.0, 0.01'), ['ConeA', 'ConeB'])


class TestPicturesAreReplaced(TestCase):
    """
    A source, event or model has one picture of each kind, and calculating it again replaces it: the
    old file is removed, and the new one doesn't get a random suffix to its name for the storage not
    having overwritten the old one. (Pictures used to pile up, one more for every calculation.)
    """

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings_override = override_settings(MEDIA_ROOT=self.media.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        self.target = Target.objects.create(name='ReplaceMe', ra=10.0, dec=10.0)
        self.event = Event.objects.create(
            target=self.target, event_id='ReplaceMe_1', start_time=2461000.0, duration=1.0)

    def files_under(self, directory):
        """The names of all the files in a folder of the media, and its folders"""
        found = []
        for root, directories, files in os.walk(os.path.join(self.media.name, directory)):
            found.extend(os.path.relpath(os.path.join(root, name), self.media.name) for name in files)
        return sorted(found)

    def png(self, text=b'x'):
        return ContentFile(b'\x89PNG\r\n\x1a\n' + text)

    def test_replace_image_file(self):
        field = self.event.thumbnail

        # The first picture
        utils.replace_image_file(field, 'ReplaceMe_lc.png', self.png(b'first'))
        first = field.name
        self.assertTrue(first.startswith('event_thumbnails/') and first.endswith('/ReplaceMe_lc.png'))
        self.assertEqual(self.files_under('event_thumbnails'), [first])

        # Replaced the same day: the same name, with no suffix, and the one file
        utils.replace_image_file(field, 'ReplaceMe_lc.png', self.png(b'second'))
        self.assertEqual(field.name, first)
        self.assertEqual(self.files_under('event_thumbnails'), [first])
        with default_storage.open(first) as image:
            self.assertTrue(image.read().endswith(b'second'))

    def test_a_picture_from_an_earlier_day_is_removed(self):
        old = default_storage.save('event_thumbnails/2020/01/01/ReplaceMe_lc.png', self.png(b'old'))
        Event.objects.filter(pk=self.event.pk).update(thumbnail=old)
        event = Event.objects.get(pk=self.event.pk)
        self.assertEqual(self.files_under('event_thumbnails'), [old])

        utils.replace_image_file(event.thumbnail, 'ReplaceMe_lc.png', self.png(b'new'))

        # One file, and it's the new one, which is where the event now says its picture is
        self.assertEqual(self.files_under('event_thumbnails'), [event.thumbnail.name])
        self.assertNotEqual(event.thumbnail.name, old)
        self.assertNotIn('2020/01/01', event.thumbnail.name)
        self.assertNotRegex(event.thumbnail.name, r'_[A-Za-z0-9]{7}\.png$')   # no suffix

    def test_a_picture_that_has_gone_is_no_problem(self):
        Event.objects.filter(pk=self.event.pk).update(thumbnail='event_thumbnails/2020/01/01/gone.png')
        event = Event.objects.get(pk=self.event.pk)

        utils.replace_image_file(event.thumbnail, 'ReplaceMe_lc.png', self.png())

        self.assertEqual(self.files_under('event_thumbnails'), [event.thumbnail.name])

    def test_each_kind_of_picture_is_replaced_when_it_is_calculated_again(self):
        # Thumbnail
        PhotometryReducedDatum.objects.bulk_create([PhotometryReducedDatum(
            target=self.target, source_name='Roman_F146', bandpass='F146', brightness=20.0, brightness_error=0.01,
            timestamp=timezone.make_aware(Time(2461000.0 + i * 0.05, format='jd').datetime, datetime.timezone.utc),
        ) for i in range(10)])
        for _ in range(3):
            event_functions.generate_event_lightcurves(Event.objects.get(pk=self.event.pk))
        thumbnails = self.files_under('event_thumbnails')
        self.assertEqual(thumbnails, [Event.objects.get(pk=self.event.pk).thumbnail.name])

        # Periodogram
        frequency = np.linspace(0.001, 10.0, 100)
        for _ in range(3):
            data_utils.generate_periodogram(Target.objects.get(pk=self.target.pk), np.ones(100), frequency)
        self.assertEqual(self.files_under('periodograms'), [Target.objects.get(pk=self.target.pk).periodogram.name])

        # Corner plot
        model = PSPLModel.objects.create(event=self.event, model_type='PSPL microlensing')
        results = {'samples': np.random.default_rng(3).normal(size=(200, 2)), 'sample_columns': [0, 1],
                   'parameter_labels': ['a', 'b']}
        for _ in range(3):
            data_utils.generate_corner_plot(EventModel.objects.get(pk=model.pk), results, 'ReplaceMe_PSPL_corner_plot.png')
        self.assertEqual(self.files_under('eventmodel_plots'), [EventModel.objects.get(pk=model.pk).corner_plot.name])
        self.assertNotRegex(thumbnails[0], r'_[A-Za-z0-9]{7}\.png$')


class TestPeriodogramImage(TestCase):
    """
    The periodogram is calculated and drawn once, as a picture kept with the source. (It isn't stored
    as data to plot again: there's a point for every frequency on a fine grid, over half a million
    for a long lightcurve, and most sources have nothing in them.)
    """

    PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings_override = override_settings(MEDIA_ROOT=self.media.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        self.target = Target.objects.create(name='PeriodicTarget', ra=10.0, dec=10.0)

    def lightcurve(self, n=400, period=2.5):
        t = np.sort(np.random.default_rng(1).uniform(0.0, 100.0, n))
        return np.column_stack([t, 20.0 + 0.1 * np.sin(2 * np.pi * t / period), np.full(n, 0.01)])

    def assertIsPNG(self, name):
        with default_storage.open(name) as image:
            self.assertEqual(image.read(8), self.PNG_SIGNATURE)

    def test_calc_periodogram_draws_it_and_keeps_the_picture_with_the_source(self):
        diagnostics_found = variable_stars.calc_periodogram(self.target, self.lightcurve(), {})

        # The periodogram's peak is that of the signal
        self.assertAlmostEqual(diagnostics_found['period'], 2.5, delta=0.05)
        self.assertGreater(diagnostics_found['max_peak_periodogram'], 0.5)

        stored = Target.objects.get(pk=self.target.pk).periodogram
        self.assertTrue(stored.name.startswith('periodograms/'))
        self.assertIn('PeriodicTarget_periodogram', stored.name)
        self.assertTrue(stored.name.endswith('.png'))
        self.assertIsPNG(stored.name)

    def test_the_picture_has_a_log_frequency_axis_and_is_not_cut_off(self):
        drawn = []
        real_close = data_utils.plt.close
        real_savefig = matplotlib.figure.Figure.savefig
        saved_with = {}

        def savefig(figure, *args, **kwargs):
            saved_with.update(kwargs)
            return real_savefig(figure, *args, **kwargs)

        with mock.patch.object(data_utils.plt, 'close', side_effect=lambda figure: (drawn.append(figure), real_close(figure))), \
                mock.patch.object(matplotlib.figure.Figure, 'savefig', autospec=True, side_effect=savefig):
            data_utils.generate_periodogram(self.target, np.ones(50), np.linspace(0.001, 10.0, 50))

        axes = drawn[0].axes[0]
        self.assertEqual(axes.get_xscale(), 'log')
        self.assertEqual(axes.get_xlabel(), 'Frequency [1/day]')
        self.assertEqual(axes.get_ylabel(), 'Power')
        # The tick labels of the y axis, and the x label, are otherwise cut off
        self.assertEqual(saved_with.get('bbox_inches'), 'tight')

    def test_the_periodogram_is_not_kept_as_data(self):
        variable_stars.calc_periodogram(self.target, self.lightcurve(), {})

        self.assertFalse(ReducedDatum.objects.filter(data_type__startswith='periodogram').exists())

    def test_nothing_is_drawn_for_a_short_lightcurve(self):
        diagnostics_found = variable_stars.calc_periodogram(self.target, self.lightcurve(n=9), {})

        self.assertEqual(diagnostics_found, {})
        self.assertFalse(Target.objects.get(pk=self.target.pk).periodogram)
        self.assertEqual(variable_stars.calc_periodogram(self.target, None, {}), {})

    def test_calculating_it_again_replaces_the_picture(self):
        variable_stars.calc_periodogram(self.target, self.lightcurve(period=2.5), {})
        first = Target.objects.get(pk=self.target.pk).periodogram.name
        with default_storage.open(first) as image:
            first_picture = image.read()

        diagnostics_found = variable_stars.calc_periodogram(self.target, self.lightcurve(period=7.0), {})

        # The same file, with the new picture in it, and no other
        second = Target.objects.get(pk=self.target.pk).periodogram.name
        self.assertEqual(second, first)
        self.assertIsPNG(second)
        with default_storage.open(second) as image:
            self.assertNotEqual(image.read(), first_picture)
        self.assertEqual(default_storage.listdir(os.path.dirname(second))[1], [os.path.basename(second)])
        self.assertAlmostEqual(diagnostics_found['period'], 7.0, delta=0.2)


@override_settings(TOM_MFA_REQUIRED=None)
class TestPeriodogramTab(TestCase):
    """The Periodogram tab of the source detail page shows the picture"""

    def setUp(self):
        self.client.force_login(User.objects.create_superuser('periodogram_user', password='x'))
        self.target = Target.objects.create(name='TabTarget', ra=10.0, dec=10.0, type='SIDEREAL')

    def get_pane(self):
        html = self.client.get(reverse('targets:detail', kwargs={'pk': self.target.pk})).content.decode()
        self.assertIn('id="periodogram-tab"', html)
        start = html.index('id="periodogram"')
        return html[start:html.index('id="manage-data"', start)], html

    def test_the_picture_is_shown(self):
        Target.objects.filter(pk=self.target.pk).update(periodogram='periodograms/2026/10/12/TabTarget_periodogram.png')

        pane, html = self.get_pane()

        self.assertIn('<img src="/data/periodograms/2026/10/12/TabTarget_periodogram.png"', pane)
        self.assertIn('alt="Source periodogram"', pane)
        self.assertNotIn('No periodogram available', pane)

    def test_without_a_periodogram(self):
        pane, html = self.get_pane()

        self.assertIn('No periodogram available', pane)
        self.assertNotIn('<img', pane)

    def test_the_picture_is_part_of_the_page(self):
        # Not loaded separately: there's nothing to fetch but the picture itself
        pane, html = self.get_pane()

        self.assertNotIn('hx-get', pane)
        self.assertNotIn('target-periodogram', html)
        with self.assertRaises(NoReverseMatch):
            reverse('target-periodogram:tab')


class TestJPLQueryRetries(TestCase):
    """Requests to JPL's services are tried again if they fail, and then skipped without failing the task"""

    class Response:
        def __init__(self, status_code, content=None):
            self.status_code, self.content = status_code, content or {}

        def json(self):
            return self.content

    def setUp(self):
        get = mock.patch('custom_code.solar_system.requests.get')
        sleep = mock.patch('custom_code.solar_system.time.sleep')
        self.get, self.sleep = get.start(), sleep.start()
        self.addCleanup(get.stop)
        self.addCleanup(sleep.stop)

        self.target = Target.objects.create(name='JPLTarget', ra=270.0, dec=-30.0)
        self.event = Event.objects.create(target=self.target, event_id='JPL_1', start_time=2461000.0, duration=2.0)

    def test_retries_a_dropped_connection_with_a_growing_delay(self):
        dropped = requests.exceptions.ConnectionError('Remote end closed connection without response')
        self.get.side_effect = [dropped, dropped, self.Response(200)]

        response = solar_system.get_with_retries('https://jpl.example/api', {'a': 1})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.get.call_count, 3)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [5.0, 10.0])
        # And never waits for ever for a response
        self.assertTrue(all(call.kwargs['timeout'] for call in self.get.call_args_list))

    def test_retries_timeouts_and_busy_servers_but_not_other_errors(self):
        self.get.side_effect = [requests.exceptions.ReadTimeout(), self.Response(503), self.Response(200)]
        self.assertEqual(solar_system.get_with_retries('https://jpl.example/api', {}).status_code, 200)
        self.assertEqual(self.get.call_count, 3)

        self.get.reset_mock()
        self.get.side_effect = [self.Response(400)]
        self.assertEqual(solar_system.get_with_retries('https://jpl.example/api', {}).status_code, 400)
        self.assertEqual(self.get.call_count, 1)

    def test_gives_up_after_the_last_attempt(self):
        self.get.side_effect = requests.exceptions.ConnectionError('down')
        with self.assertRaises(requests.exceptions.ConnectionError):
            solar_system.get_with_retries('https://jpl.example/api', {})
        self.assertEqual(self.get.call_count, solar_system.QUERY_ATTEMPTS)
        self.assertEqual(self.sleep.call_count, solar_system.QUERY_ATTEMPTS - 1)   # none after the last

        # A server that stays busy returns its last response, for the caller to deal with
        self.get.reset_mock()
        self.get.side_effect = [self.Response(503)] * solar_system.QUERY_ATTEMPTS
        self.assertEqual(solar_system.get_with_retries('https://jpl.example/api', {}).status_code, 503)

    def test_moving_object_search_skips_quietly_when_jpl_is_unreachable(self):
        self.get.side_effect = requests.exceptions.ConnectionError('down')

        with self.assertLogs('custom_code.solar_system', level='WARNING') as logs:
            tasks.check_event_for_moving_objects.call(self.event.pk)    # no exception

        self.assertEqual(self.get.call_count, solar_system.QUERY_ATTEMPTS)
        self.assertTrue(any('skipping the moving object search' in line for line in logs.output))
        self.event.refresh_from_db()
        self.assertIsNone(self.event.nearest_moving_object)

    def test_moving_object_search_skips_if_horizons_gives_no_position(self):
        self.get.side_effect = [self.Response(500)] * solar_system.QUERY_ATTEMPTS

        with self.assertLogs('custom_code.solar_system', level='WARNING'):
            solar_system.find_moving_objects_near_event(self.event)

        # The second service isn't asked about a position that isn't known
        self.assertEqual(self.get.call_count, solar_system.QUERY_ATTEMPTS)

    def test_moving_object_found_after_a_retry_is_stored(self):
        vector = {'X': 1.0, 'Y': 2.0, 'Z': 3.0, 'VX': 0.1, 'VY': 0.2, 'VZ': 0.3}
        self.get.side_effect = requests.exceptions.ConnectionError('down')
        with mock.patch('custom_code.solar_system.query_horizons_for_roman', return_value=vector), \
                mock.patch('custom_code.solar_system.query_sbident_for_event', return_value=('433 Eros', 1.5)):
            solar_system.find_moving_objects_near_event(self.event)

        self.event.refresh_from_db()
        self.assertEqual(self.event.nearest_moving_object, '433 Eros')
        self.assertAlmostEqual(self.event.angular_separation_moving_object, 1.5 / 3600.0)


class TestBackgroundTasks(TestCase):
    """A task queued for a row that has since been deleted ends quietly instead of failing"""

    def setUp(self):
        self.target = Target.objects.create(name='TaskTarget', ra=10.0, dec=10.0)
        self.event = Event.objects.create(target=self.target, event_id='TASK_1', start_time=2460000.0, duration=2.0)

    def test_tasks_run_for_existing_rows(self):
        for task, work, row in [
            (tasks.check_event_for_moving_objects, 'find_moving_objects_near_event', self.event),
            (tasks.make_event_lightcurve, 'generate_event_lightcurves', self.event),
        ]:
            with self.subTest(task=work), mock.patch(f'custom_code.tasks.{work}') as mocked:
                task.call(row.pk)
                self.assertEqual(mocked.call_count, 1)
                self.assertEqual(mocked.call_args.args[0].pk, row.pk)

    def test_tasks_for_deleted_rows_do_nothing(self):
        target_pk, event_pk = self.target.pk, self.event.pk
        self.event.delete()
        self.target.delete()

        for task, work, pk in [
            (tasks.check_event_for_moving_objects, 'find_moving_objects_near_event', event_pk),
            (tasks.make_event_lightcurve, 'generate_event_lightcurves', event_pk),
        ]:
            with self.subTest(task=work), mock.patch(f'custom_code.tasks.{work}') as mocked:
                task.call(pk)   # no DoesNotExist
                mocked.assert_not_called()


class AlertPacketMixin:
    """A synthetic MSOS alert packet"""

    def packet(self):
        t = np.linspace(2460000.0, 2460010.0, 60)
        band = {'time': t.tolist(), 'flux': np.full(60, 1000.0).tolist(), 'flux_err': np.full(60, 10.0).tolist()}
        return {
            'id': '12345', 'objname': 'IngestTest', 'ra': 270.0, 'dec': -30.0,
            'metadata': {'t0lens1': 2460005.0, 'u0lens1': 0.1, 'tE_ref': 1.0, 'rho': 0.01,
                         'Source_F146': 20.0, 'EventID': 7.0},
            'light_curves': {'F087': band, 'F146': band, 'F213': band},
        }


class TestIngestAlert(AlertPacketMixin, TestCase):
    """Ingesting the same alert packet again must not record it again"""

    def ingest(self, data):
        serial = MSOSAlertSerializer(data=data)
        serial.is_valid(raise_exception=True)
        # Tasks are queued once the transaction commits, which a TestCase never does by itself
        with self.captureOnCommitCallbacks(execute=True):
            serial.save()
        return serial

    def test_repeat_ingest_finds_existing_alert(self):
        first = self.ingest(self.packet())
        self.assertEqual(RGESAlert.objects.count(), 1)
        # The peak magnitude is estimated after the alert is created, so it no longer has
        # its initial value, and the ingest timestamp is different each time
        self.assertNotEqual(RGESAlert.objects.get().alert_peak_mag, 0.0)

        second = self.ingest(self.packet())

        self.assertEqual(RGESAlert.objects.count(), 1)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Target.objects.filter(name='IngestTest').count(), 1)
        self.assertEqual(second.alert.pk, first.alert.pk)
        self.assertEqual(first.alert.target, first.target)

        # Each task was queued once per row, not again for the repeat ingest
        queued = Counter(DBTaskResult.objects.values_list('task_path', flat=True))
        self.assertEqual({path.split('.')[-1]: n for path, n in queued.items()}, {
            'compute_source_diagnostics': 1,
            'check_event_for_moving_objects': 1, 'make_event_lightcurve': 1,
        })

        # A different alert for the same source is recorded
        other = self.packet()
        other['id'] = '12346'
        self.ingest(other)
        self.assertEqual(RGESAlert.objects.count(), 2)
        self.assertEqual(Event.objects.count(), 2)


class TestSettingsEnvironment(TestCase):
    """A blank line in a .env file sets the variable to nothing, which is to mean its default"""

    def database_settings(self, **environment):
        env = {**os.environ, 'SECRET_KEY': 'x', 'DJANGO_SETTINGS_MODULE': 'rogue_db.settings', **environment}
        result = subprocess.run(
            [sys.executable, '-c',
             'from django.conf import settings; d = settings.DATABASES["default"]; '
             'print(d["NAME"], d["USER"], d["HOST"], d["PORT"], sep="|")'],
            capture_output=True, text=True, env=env, cwd=os.getcwd(),
        )
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        return result.stdout.strip()

    def test_blank_database_settings_are_the_defaults(self):
        blank = dict(DB_NAME='', DB_USER='', DB_HOST='', DB_PORT='', DB_PASS='')

        self.assertEqual(self.database_settings(**blank), 'rogue_tom_db|postgres|127.0.0.1|5432')

    def test_database_settings_from_the_environment(self):
        given = dict(DB_NAME='mydb', DB_USER='me', DB_HOST='db', DB_PORT='5433')

        self.assertEqual(self.database_settings(**given), 'mydb|me|db|5433')


class TestRegistrationEmails(TestCase):
    """
    The registration emails are the project's own. The toolkit renders them as account/email/...,
    so they're only used where they're at templates/account/email/.
    """

    NAMES = ['registration_approved_subject.txt', 'registration_approved_message.txt',
             'registration_requested_subject.txt', 'registration_requested_message.txt']

    def test_the_templates_used_are_the_projects(self):
        from django.conf import settings
        from django.template.loader import get_template

        for name in self.NAMES:
            origin = get_template('account/email/' + name).origin.name
            self.assertTrue(origin.startswith(os.path.join(settings.BASE_DIR, 'templates')), origin)

    def test_approval_email(self):
        from django.template.loader import render_to_string

        context = {'user': User(username='newuser'), 'tom_name': 'RogueDB', 'login_url': 'https://rogue/login/'}

        message = render_to_string('account/email/registration_approved_message.txt', context)

        self.assertIn('Thank you for registering for RogueDB.', message)
        self.assertIn('https://rogue/login/', message)
        self.assertIn('multi-factor authentication', message)

    def test_request_email_subject(self):
        from django.template.loader import render_to_string

        subject = render_to_string('account/email/registration_requested_subject.txt',
                                   {'user': User(username='newuser')}).strip()

        self.assertEqual(subject, 'New RogueDB account registration awaiting approval: newuser')


class TestIngestUniqueness(AlertPacketMixin, TestCase):
    """
    The ingest looks an event and an alert up by their identity, and makes them if they aren't there.
    With two ingests running at once (parallel workers) both can find nothing and go on to make
    one, which only the database can prevent.
    """

    def setUp(self):
        self.target = Target.objects.create(name='UniqueTarget', ra=10.0, dec=10.0)
        self.event = Event.objects.create(
            target=self.target, event_id='UniqueTarget_1', start_time=2460000.0, duration=2.0)
        self.alert = RGESAlert.objects.create(
            alert_id=1, roman_id='UniqueTarget', event=self.event, alert_origin='MSOS')

    def test_an_event_id_is_used_once(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Event.objects.create(target=self.target, event_id='UniqueTarget_1', start_time=1.0, duration=1.0)

        # ...and the ingest, having lost the race to make it, finds the one that won
        found, created = Event.objects.get_or_create(event_id='UniqueTarget_1', defaults=dict(target=self.target))
        self.assertFalse(created)
        self.assertEqual(found.pk, self.event.pk)

    def test_an_alert_is_recorded_once(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RGESAlert.objects.create(alert_id=1, roman_id='UniqueTarget', event=self.event, alert_origin='MSOS')

        # Different in any of the four is a different alert
        self.assertEqual(RGESAlert.objects.count(), 1)
        RGESAlert.objects.create(alert_id=2, roman_id='UniqueTarget', event=self.event, alert_origin='MSOS')
        RGESAlert.objects.create(alert_id=1, roman_id='UniqueTarget', event=self.event, alert_origin='Aethra')
        other = Event.objects.create(target=self.target, event_id='UniqueTarget_2', start_time=1.0, duration=1.0)
        RGESAlert.objects.create(alert_id=1, roman_id='UniqueTarget', event=other, alert_origin='MSOS')
        self.assertEqual(RGESAlert.objects.count(), 4)

    def test_events_without_an_id_are_not_the_same_event(self):
        Event.objects.create(target=self.target, start_time=1.0, duration=1.0)
        Event.objects.create(target=self.target, start_time=2.0, duration=1.0)

        self.assertEqual(Event.objects.filter(event_id=None).count(), 2)


class TestIngestAlertsCommand(AlertPacketMixin, TestCase):
    """The function each worker of ingest_alerts runs, for one alert file"""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.alert_file = os.path.join(self.directory.name, 'alert.json')
        with open(self.alert_file, 'w') as f:
            json.dump(self.packet(), f)

    def ingest(self):
        from custom_code.management.commands import ingest_alerts
        with mock.patch.object(event_functions, 'run_event_modeling') as modeling:
            result = ingest_alerts.ingest_alert_and_model_event(self.alert_file)
        return result, modeling

    def test_an_alert_ingested_before_is_modeled_again(self):
        first, first_modeling = self.ingest()
        second, second_modeling = self.ingest()

        self.assertTrue(first)
        self.assertTrue(second)
        self.assertEqual(RGESAlert.objects.count(), 1)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(PhotometryReducedDatum.objects.count(), 3 * 60)
        # The event modeled is the one that's in the database
        event = Event.objects.get()
        self.assertEqual(first_modeling.call_args.args, (event,))
        self.assertEqual(second_modeling.call_args.args, (event,))

    def test_a_failed_ingest_is_not_modeled(self):
        from custom_code.management.commands import ingest_alerts
        from django.db.utils import IntegrityError

        with mock.patch.object(MSOSAlertSerializer, 'save', side_effect=IntegrityError('clash')), \
                mock.patch.object(event_functions, 'run_event_modeling') as modeling:
            with self.assertRaises(IntegrityError):
                ingest_alerts.ingest_alert_and_model_event(self.alert_file)

        modeling.assert_not_called()


class TestIngestTaskOrdering(AlertPacketMixin, TransactionTestCase):
    """
    The tasks that need an alert's lightcurve (the source diagnostics, the event's lightcurve
    plot) must not be queued until it has been stored. A TransactionTestCase, as the order
    only shows when transactions really commit, which a TestCase never does.
    """

    def record_photometry_at_queuing(self):
        """How many photometry rows were stored as each task was queued, by task name"""
        seen = {}

        def record(sender, task_result, **kwargs):
            seen[task_result.task.func.__name__] = PhotometryReducedDatum.objects.count()

        task_enqueued.connect(record)
        self.addCleanup(task_enqueued.disconnect, record)
        return seen

    def test_without_the_transaction_tasks_are_queued_too_early(self):
        # The control for the test below: the same ingest, minus the transaction decorating create()
        seen = self.record_photometry_at_queuing()
        serial = MSOSAlertSerializer(data=self.packet())
        serial.is_valid(raise_exception=True)

        MSOSAlertSerializer.create.__wrapped__(serial, serial.validated_data)

        self.assertEqual(seen['compute_source_diagnostics'], 0)
        self.assertEqual(seen['make_event_lightcurve'], 0)

    def test_tasks_are_queued_once_the_photometry_is_stored(self):
        seen = self.record_photometry_at_queuing()

        serial = MSOSAlertSerializer(data=self.packet())
        serial.is_valid(raise_exception=True)
        serial.save()

        self.assertEqual(PhotometryReducedDatum.objects.count(), 3 * 60)
        self.assertEqual(set(seen), {'compute_source_diagnostics', 'check_event_for_moving_objects',
                                     'make_event_lightcurve'})
        for task_name, nphotometry in seen.items():
            self.assertEqual(nphotometry, 3 * 60, task_name)

    def test_nothing_is_queued_if_the_ingest_fails(self):
        packet = self.packet()
        packet['light_curves']['F146']['flux_err'] = packet['light_curves']['F146']['flux_err'][:-1]
        queued = []
        task_enqueued.connect(lambda sender, task_result, **kw: queued.append(task_result))

        serial = MSOSAlertSerializer(data=packet)
        serial.is_valid(raise_exception=True)
        with self.assertRaises(Exception):
            serial.save()

        # Rolled back whole, rather than leaving a source and event without their data
        self.assertEqual(Target.objects.filter(name='IngestTest').count(), 0)
        self.assertEqual(Event.objects.count(), 0)
        self.assertEqual(queued, [])


class TestSourceDiagnostics(TestCase):
    """run_source_diagnostics records a new SourceDiagnostics entry for a source"""

    def setUp(self):
        self.target, self.event, self.ndata, self.nlc, self.datums = create_test_target_with_photometry()

    def test_run_source_diagnostics(self):
        entry = source_functions.run_source_diagnostics(self.target)

        self.assertEqual(SourceDiagnostics.objects.get(target=self.target), entry)
        self.assertAlmostEqual(entry.baseline_magnitude, 17.0)
        self.assertEqual(entry.baseline_mag_passband, 'Roman_F146')
        self.assertEqual(entry.nearest_variable_star, '')
        # The periodogram of the 100 points
        self.assertIsNotNone(entry.period)
        self.assertIsNotNone(entry.max_peak_periodogram)

    def test_each_run_adds_an_entry_and_the_latest_is_used(self):
        source_functions.run_source_diagnostics(self.target)
        PhotometryReducedDatum.objects.filter(target=self.target).update(brightness=18.0)
        latest = source_functions.run_source_diagnostics(self.target)

        self.assertEqual(SourceDiagnostics.objects.filter(target=self.target).count(), 2)
        self.assertAlmostEqual(latest.baseline_magnitude, 18.0)
        self.assertEqual(SourceDiagnostics.objects.filter(target=self.target).order_by('-created_at').first(), latest)

    def test_source_without_photometry(self):
        target = Target.objects.create(name='NoPhotometry', ra=10.0, dec=10.0)

        entry = source_functions.run_source_diagnostics(target)

        self.assertEqual(entry.baseline_magnitude, 0.0)
        self.assertEqual(entry.baseline_mag_passband, '')
        self.assertEqual(SourceDiagnostics.objects.filter(target=target).count(), 1)


class TestBaselineMagnitude(TestCase):

    def test_without_a_lightcurve(self):
        for lightcurve in (None, np.empty((0, 3))):
            result = diagnostics.calc_baseline_magnitude(lightcurve, 'Roman_F146', {'baseline_magnitude': 0.0})
            self.assertEqual(result, {'baseline_magnitude': 0.0})

    def test_with_a_lightcurve(self):
        lightcurve = np.array([[1.0, 20.0, 0.1], [2.0, 21.0, 0.1], [3.0, 20.5, 0.1]])
        result = diagnostics.calc_baseline_magnitude(lightcurve, 'Roman_F146', {})
        self.assertEqual(result['baseline_magnitude'], 20.5)
        self.assertEqual(result['baseline_mag_passband'], 'Roman_F146')


class TestVariableStars(TestCase):

    def setUp(self):
        self.test_target, self.test_event, self.ndata, self.nlc, self.datums = create_test_target_with_photometry()
        self.datasets = data_utils.get_full_lightcurve(self.test_target, bandpass='Roman_F146')
        self.lightcurve = data_utils.fetch_lightcurve(self.datasets)
        self.diagnostics = {
            'classification': 'Microlensing PSPL',
            'category': 'Microlensing stellar/planet',
            'source_magnitude': 0.0,
            'source_mag_error': 0.0,
            'baseline_magnitude': 0.0,
            'baseline_mag_error': 0.0,
            'nearest_flare_star': '',
            'angular_separation_flare_star': 0.0,
            'nearest_variable_star': '',
            'angular_separation_variable': 0.0,
            'nearest_variable_type': '',
            'max_peak_periodogram': 0.0,
            'period': 0.0
        }

    def test_calc_periodogram(self):
        diagnostics = variable_stars.calc_periodogram(self.test_target, self.lightcurve, self.diagnostics)

        assert(diagnostics['max_peak_periodogram'] != 0.0)
        assert(diagnostics['period'] != 0.0)

    def test_calc_baseline_magnitude(self):
        results = diagnostics.calc_baseline_magnitude(
            self.lightcurve,
            'Roman_F146',
            self.diagnostics
        )

        baseline = np.median(np.array([x.brightness for x in self.datums]))

        self.assertAlmostEqual(results['baseline_magnitude'], baseline, 0.1)

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

        diagnostics.second_peak_diagnostics(self.test_event)

        test_event = Event.objects.get(pk=self.test_event.pk)

        midpoint = self.test_event.start_time + self.test_event.duration/2.0
        midpoint2 = self.test_event2.start_time + self.test_event2.duration/2.0
        dt = abs(midpoint - midpoint2)
        self.assertAlmostEqual(test_event.time_to_second_peak, dt, 2)
        self.assertAlmostEqual(test_event.second_peak_mag, self.test_event2.peak_mag)

    def test_second_peak_diagnostics_survive_saving_the_event(self):
        # The modeling pipeline goes on to save() the Event instance it passes to the diagnostics
        diagnostics.second_peak_diagnostics(self.test_event)
        self.assertIsNotNone(self.test_event.time_to_second_peak)

        self.test_event.delta_chi2_PSPL = 3.0
        self.test_event.save()

        test_event = Event.objects.get(pk=self.test_event.pk)
        self.assertIsNotNone(test_event.time_to_second_peak)
        self.assertIsNotNone(test_event.second_peak_mag)
        self.assertEqual(test_event.delta_chi2_PSPL, 3.0)

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
            target = Target.objects.create(name=name, ra=ra, dec=10.0)
            SourceDiagnostics.objects.create(
                target=target, nearest_variable_type=variable_type, baseline_magnitude=20.0, period=ra / 100.0)
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

    def make_diagnostics(self, name, created, **values):
        """A SourceDiagnostics entry for a source, made at a given moment"""
        target = Target.objects.get(name=name)
        entry = SourceDiagnostics.objects.create(target=target, **values)
        SourceDiagnostics.objects.filter(pk=entry.pk).update(created_at=created)
        return entry

    def test_source_parameters_use_the_latest_diagnostics(self):
        utc = datetime.timezone.utc
        # Both sources' entries from setUp are made now. A has an older one too, with another
        # type and baseline; B has a newer one.
        self.make_diagnostics('CutfileA', datetime.datetime(2025, 1, 1, tzinfo=utc),
                              nearest_variable_type='Algol', baseline_magnitude=15.0)
        self.make_diagnostics('CutfileB', datetime.datetime(2099, 1, 1, tzinfo=utc),
                              nearest_variable_type='Cepheid', baseline_magnitude=10.0, period=2.0)

        base = 'model_type=pspl&'
        self.assertEqual(self.search(base + 'source_nearest_variable_type=rrlyr'), ['CutfileA'])
        self.assertEqual(self.search(base + 'source_nearest_variable_type=algol'), [])
        self.assertEqual(self.search(base + 'source_nearest_variable_type=mira'), [])
        self.assertEqual(self.search(base + 'source_nearest_variable_type=cepheid'), ['CutfileB'])

        # Numbers likewise, with the two bounds applying to the same entry
        self.assertEqual(self.search(base + 'source_baseline_magnitude_min=19'), ['CutfileA'])
        self.assertEqual(self.search(base + 'source_baseline_magnitude_max=12'), ['CutfileB'])
        self.assertEqual(self.search(base + 'source_baseline_magnitude_min=19&source_baseline_magnitude_max=21'),
                         ['CutfileA'])
        self.assertEqual(self.search(base + 'source_baseline_magnitude_min=14&source_baseline_magnitude_max=16'), [])

        # With the source's own position, and diagnostics criteria on different parameters
        self.assertEqual(self.search(base + 'source_ra_max=150&source_nearest_variable_type=rrlyr'), ['CutfileA'])
        self.assertEqual(self.search(base + 'source_period_min=1.5&source_nearest_variable_type=cepheid'),
                         ['CutfileB'])

    def test_latest_diagnostics_of_equal_age_is_the_last_made(self):
        moment = datetime.datetime(2099, 1, 1, tzinfo=datetime.timezone.utc)
        self.make_diagnostics('CutfileA', moment, nearest_variable_type='First')
        self.make_diagnostics('CutfileA', moment, nearest_variable_type='Second')
        self.assertEqual(self.search('model_type=pspl&source_nearest_variable_type=second'), ['CutfileA'])
        self.assertEqual(self.search('model_type=pspl&source_nearest_variable_type=first'), [])

    def test_source_without_diagnostics(self):
        target = Target.objects.create(name='CutfileC', ra=300.0, dec=10.0)
        event = Event.objects.create(target=target, event_id='CutfileC-1', start_time=2460000.0, duration=1.0)
        PSPLModel.objects.create(event=event, model_type='PSPL microlensing', tE=1.0, chisq=1.0)

        # Found by anything that isn't about the diagnostics, but not by their thresholds
        self.assertEqual(self.search('model_type=pspl'), ['CutfileA', 'CutfileB', 'CutfileC'])
        self.assertEqual(self.search('model_type=pspl&source_ra_min=250'), ['CutfileC'])
        self.assertEqual(self.search('model_type=pspl&source_baseline_magnitude_min=0'), ['CutfileA', 'CutfileB'])
        self.assertEqual(self.search('model_type=pspl&source_nearest_variable_type=rr'), ['CutfileA'])

    def test_source_parameters_as_of_a_moment_use_the_diagnostics_then(self):
        utc = datetime.timezone.utc
        EventModel.objects.update(created_at=datetime.datetime(2020, 1, 1, tzinfo=utc))
        # A's diagnostics were revised in 2026 (setUp's entries are made now); B's were first made then
        self.make_diagnostics('CutfileA', datetime.datetime(2025, 1, 1, tzinfo=utc),
                              nearest_variable_type='Algol', baseline_magnitude=15.0)
        SourceDiagnostics.objects.filter(target__name='CutfileB').update(
            created_at=datetime.datetime(2026, 1, 1, tzinfo=utc))
        before, after = 'as_of=2025-06-01T00:00:00Z', 'as_of=2026-06-01T00:00:00Z'
        base = 'model_type=pspl&'

        # In mid-2025 A was an Algol type with a baseline of 15, and B had no diagnostics
        self.assertEqual(self.search(base + before + '&source_nearest_variable_type=algol'), ['CutfileA'])
        self.assertEqual(self.search(base + before + '&source_nearest_variable_type=rrlyr'), [])
        self.assertEqual(self.search(base + before + '&source_baseline_magnitude_max=16'), ['CutfileA'])
        self.assertEqual(self.search(base + before), ['CutfileA', 'CutfileB'])   # no source criteria

        # By mid-2026 both had the entries made then (A's from setUp is later still)
        self.assertEqual(self.search(base + after + '&source_nearest_variable_type=algol'), ['CutfileA'])
        self.assertEqual(self.search(base + after + '&source_nearest_variable_type=mira'), ['CutfileB'])

        # And with no cutoff, the latest of all
        self.assertEqual(self.search(base + 'source_nearest_variable_type=algol'), [])
        self.assertEqual(self.search(base + 'source_nearest_variable_type=rrlyr'), ['CutfileA'])

    @override_settings(TOM_MFA_REQUIRED=None)
    def test_export_source_uses_the_latest_diagnostics(self):
        utc = datetime.timezone.utc
        self.make_diagnostics('CutfileA', datetime.datetime(2025, 1, 1, tzinfo=utc),
                              nearest_variable_type='Algol', baseline_magnitude=15.0)
        self.client.force_login(User.objects.create_user('cutfile_user'))
        url = reverse('cutfiles:list') + '?model_type=pspl&export=json'

        sources = {r['source']['name']: r['source'] for r in self.client.get(url).json()['results']}
        self.assertEqual(sources['CutfileA']['nearest_variable_type'], 'RRLyr')
        self.assertEqual(sources['CutfileA']['baseline_magnitude'], 20.0)
        self.assertEqual(sources['CutfileA']['ra'], 100.0)
        self.assertEqual(sources['CutfileB']['nearest_variable_type'], 'Mira')

        # A source with no diagnostics has no values for them
        SourceDiagnostics.objects.filter(target__name='CutfileB').delete()
        sources = {r['source']['name']: r['source'] for r in self.client.get(url).json()['results']}
        self.assertIsNone(sources['CutfileB']['nearest_variable_type'])
        self.assertEqual(sources['CutfileB']['ra'], 200.0)

        # As of a moment, the entry then
        EventModel.objects.update(created_at=datetime.datetime(2020, 1, 1, tzinfo=utc))
        data = self.client.get(url + '&as_of=2025-06-01T00:00:00Z').json()
        sources = {r['source']['name']: r['source'] for r in data['results']}
        self.assertEqual(sources['CutfileA']['nearest_variable_type'], 'Algol')
        self.assertEqual(sources['CutfileA']['baseline_magnitude'], 15.0)

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
        # The model has its MCMC chains and corner plot stored, and its event a thumbnail
        EventModel.objects.filter(event__event_id='CutfileA-1').update(
            mcmc_chains='arrays/2026/10/11/CutfileA-1_PSPL_mcmc_chains.npy',
            corner_plot='eventmodel_plots/2026/10/11/CutfileA-1_PSPL_corner_plot.png')

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
        self.assertNotIn('mcmc_chains', result['model'])
        self.assertNotIn('mcmc_chains', json.dumps(data))

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
