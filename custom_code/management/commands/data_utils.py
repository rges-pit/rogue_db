from tom_dataproducts.models import PhotometryReducedDatum, ReducedDatum
import numpy as np
import logging
from custom_code.models import (PSPLModel, FSPLModel, StraightLineModel, Event,
                                DavenportFlareModel, PitkinFlareModel)
from datetime import datetime, UTC
from astropy.time import Time
import json

logger = logging.getLogger(__name__)


def get_reduced_data(event, bandpass=None):
    """Function to extract the timeseries data from a QuerySet of PhotometryReducedDatums, and
    creates the necessary arrays.
    Also accepts a QuerySet of generic ReducedDatums (lc_model, tabular, etc.) for the same
    target, used to identify pre-existing derived datasets.
    Note that the querysets must be provided separately and not derived directly from a query
    """

    if bandpass:
        photometry_qs = PhotometryReducedDatum.objects.filter(
            target__name=event.target.name, source_name=bandpass
        ).order_by("timestamp")
    else:
        photometry_qs = PhotometryReducedDatum.objects.filter(
            target__name=event.target.name
        ).order_by("timestamp")
    datasets = {}

    # Select only those datapoints from the lightcurves that lie within the event window
    for rd in photometry_qs:
        ts = Time(rd.timestamp).jd
        if ts >= event.start_time and ts <= event.start_time + event.duration:
            # Identify different lightcurves from the filter label given
            passband = rd.bandpass
            if passband in datasets.keys():
                lc = datasets[passband]
            else:
                lc = []

            # Append the datapoint to the corresponding dataset
            try:
                lc.append([ts, rd.brightness, rd.brightness_error])
            except:
                # Necessary to handle the datapoints where only a limit is available.
                # Skipping these for now
                try:
                    lc.append([ts, rd.brightness, 1.0])
                except KeyError:
                    pass

            datasets[passband] = lc

    # Convert the accumulated lightcurves into numpy arrays:
    for passband, lc in datasets.items():
        datasets[passband] = np.array(lc)

    logger.info('Found ' + str(len(datasets)) + ' datasets')

    return datasets

def get_baseline_data(source):
    """
    Function to retrieve the full lightcurve of the source, removing those sections of it
    which are flagged as events

    Parameters:
        source  Target  RogueTarget object

    Returns:
        datasets dict   Dictionary of lightcurve arrays
    """

    # Extract the full available photometry
    photometry_qs = PhotometryReducedDatum.objects.filter(target__name=source.name).order_by("timestamp")

    # Extract the known set of events for this source
    events_qs = Event.objects.filter(target=source)

    datasets = {}

    # Select only those datapoints from the lightcurves that lie outside the event windows
    for rd in photometry_qs:
        ts = Time(rd.timestamp).jd
        for event in events_qs:
            if ts < event.start_time or ts > event.start_time + event.duration:
                # Identify different lightcurves from the filter label given
                passband = rd.bandpass
                if passband in datasets.keys():
                    lc = datasets[passband]
                else:
                    lc = []

                # Append the datapoint to the corresponding dataset
                try:
                    lc.append([ts, rd.brightness, rd.brightness_error])
                except:
                    # Necessary to handle the datapoints where only a limit is available.
                    # Skipping these for now
                    try:
                        lc.append([ts, rd.brightness, 1.0])
                    except KeyError:
                        pass

                datasets[passband] = lc

    # Convert the accumulated lightcurves into numpy arrays:
    for passband, lc in datasets.items():
        datasets[passband] = np.array(lc)

    logger.info('Found ' + str(len(datasets)) + ' datasets')

    return datasets


def fetch_lightcurve(datasets):
    """
    Function to extract the prioritized single lightcurve from a set of multiple datasets.
    This is used when a fitting function is designed to handle a single lightcurve,
    and the lightcurves are not normalized.
    """

    # If a dataset_id is given, extract the lightcurve data as an array.
    # If not, extract the first lightcurve found from the following
    # passbands in order of priority
    lightcurve = np.zeros(1)
    priority_order = ['W146', 'F184', 'F213', 'I', 'OGLE-I', 'ip', 'G', 'i_ZTF', 'r_ZTF', 'R', 'g_ZTF', 'gp']

    dataset_order = [passband for passband in priority_order if passband in datasets.keys()]

    if len(dataset_order) > 0:
        lightcurve = extract_photometry_from_dataset(datasets, dataset_order[0])

    return lightcurve

def extract_photometry_from_dataset(datasets, dataset_id, emag_limit=None):
    """
    Function to extract the photometry from a single dataset

    Returns:
        lightcurve  array with columns 'time', 'mag', 'err_mag'
    """

    photometry = datasets[dataset_id]

    # Enabling optional filtering for datapoints of low photometric precision
    if emag_limit:
        mask = (np.abs(photometry[:, -2].astype(float)) < emag_limit)
    else:
        mask = (np.abs(photometry[:, -2].astype(float)) < 99.0)

    return photometry[mask].astype(float)

def store_model_lightcurve(event, pyLIMA_results, model_type):
    """Function to store in the TOM the timeseries lightcurve corresponding to a fitted model.
    The input is a model fit object from PyLIMA.

    Note that this function has to be separate from the MicrolensingTarget class because it uses the
    ReducedDatum objects.  Circular imports result if you try to import ReducedDatums from the Target object
    """

    model_time = datetime.now(UTC)

    # Map array -> database keywords
    model_types_list = {
        'pspl': 'PSPL Microlensing',
        'fspl': 'FSPL Microlensing'
    }

    # Extract the model lightcurve timeseries from the PyLIMA fit object
    model_tel = pyLIMA_results['model_telescope_' + model_type]
    data = {
        'lc_model_time': model_tel.lightcurve['time'].value.tolist(),
        'lc_model_magnitude': model_tel.lightcurve['mag'].value.tolist()
    }

    # If there is no existing model for this target, create one
    data_type = 'lc_model_' + str(event.event_id) + '_' + model_types_list[model_type]
    qs = ReducedDatum.objects.filter(target=event.target, data_type=data_type)
    if qs.count() == 0:
        rd = ReducedDatum.objects.create(
            timestamp=model_time,
            value=data,
            source_name='RogueDB',
            source_location=event.target.name,
            data_type=data_type,
            target=event.target
        )
        logger.info('Created lightcurve model datum for ' + event.target.name)

    # If there is a pre-existing model, update it
    else:
        rd = qs[0]
        rd.timestamp = model_time
        rd.value = data
        rd.source_name = 'RogueDB'
        rd.source_location = event.target.name
        rd.data_type = 'lc_model'
        rd.target = event.target
        rd.save()
        logger.info('Updated existing lightcurve model datum for ' + event.target.name)

    return event

def store_microlensing_model_parameters(event, pylima_results):
    """Function to store the fitted model parameters in the TOM"""

    # Store the best-fit model parameters on the Target object
    parameters = ['t0', 't0_error', 'u0', 'u0_error', 'tE', 'tE_error',
                  'piEN', 'piEN_error', 'piEE', 'piEE_error',
                  'source_magnitude', 'source_mag_error',
                  'blend_magnitude', 'blend_mag_error',
                  'baseline_magnitude', 'baseline_mag_error',
                  'fit_covariance', 'chi2', 'red_chi2',
                  'ks_test', 'ad_test', 'sw_test']

    for key in parameters:
        if key in pylima_results['best_model'].keys():
            if key == 'fit_covariance':
                payload = json.dumps(pylima_results['best_model']['fit_covariance'].tolist())
                data = {'covariance': payload}
            else:
                # Intercept NaN values as these are not well supported by Django FloatFields
                if np.isnan(pylima_results['best_model'][key]):
                    data = 0.0
                else:
                    data = pylima_results['best_model'][key]
            setattr(event.target, key, data)
    event.target.save()

    # Fetch existing PSPL and FSPL models for this event, or create them,
    # and update them with the fitted parameters
    pspl_model = fetch_microlensing_model(event, 'PSPL microlensing')
    update_microlensing_model(pspl_model, pylima_results['pspl'])
    fspl_model = fetch_microlensing_model(event, 'FSPL microlensing')
    update_microlensing_model(fspl_model, pylima_results['fspl'])

    logger.info('Stored model parameters for event ' + event.target.name)

def fetch_microlensing_model(event, model_type):
    """
    Function to check to see if the given event has an existing model of the given type;
    if so, this entry will be updated; otherwise a new one will be created.
    If an unrecognised model_type is passed, None will be returned

    Parameters:
        event   Event object
        model_type  string   Microlensing model type descriptor

    Returned:
        mulens_model    PSPLModel, FSPLModel or None
    """

    mulens_model = None

    if model_type == 'PSPL microlensing':
        qs = PSPLModel.objects.filter(
            event=event,
            model_type='PSPL microlensing'
        )
    elif model_type == 'FSPL microlensing':
        qs = FSPLModel.objects.filter(
            event=event,
            model_type='FSPL microlensing'
        )

    if qs.count() == 0:
        if model_type == 'PSPL microlensing':
            mulens_model = PSPLModel.objects.create(
                event=event,
                model_type='PSPL microlensing'
            )
        elif model_type == 'FSPL microlensing':
            mulens_model = FSPLModel.objects.create(
                event=event,
                model_type='FSPL microlensing'
            )
        logger.info('Created ' + mulens_model.model_type + ' model for event ' + event.target.name)

    else:
        mulens_model = qs[0]
        logger.info('Retrieved ' + mulens_model.model_type + ' model for event ' + event.target.name)

    return mulens_model


def update_microlensing_model(mulens_model, fit_results):
    """
    Update the provided microlensing Model object, which may be of any type, with
    the dictionary of fitted results.  Note that the type of the Model and results must match.
    If an unknown type of model is requested, mulens_model = None and no action will be taken.
    """

    if mulens_model:
        mulens_model.t0 = fit_results['t0']
        mulens_model.t0_error = fit_results['t0_error']
        mulens_model.u0 = fit_results['u0']
        mulens_model.u0_error = fit_results['u0_error']
        mulens_model.tE = fit_results['tE']
        mulens_model.tE_error = fit_results['tE_error']
        mulens_model.piEN = fit_results['piEN']
        mulens_model.piEN_error = fit_results['piEN_error']
        mulens_model.piEE = fit_results['piEE']
        mulens_model.piEE_error = fit_results['piEE_error']
        if mulens_model.model_type == 'FSPL microlensing':
            mulens_model.rho = fit_results['rho']
            mulens_model.rho_error = fit_results['rho_error']
        mulens_model.chisq = fit_results['chi2']
        mulens_model.BIC = fit_results['BIC']
        mulens_model.save()

        logger.info('Stored ' + mulens_model.model_type
                    + ' model parameters for event ' + mulens_model.event.target.name)

def store_event_straightline_model_parameters(event, results):

    # If there is an existing straight line fit in the database for this event,
    # update it; otherwise create a new entry
    qs = StraightLineModel.objects.filter(
        event=event,
        model_type='Straight line'
    )

    if qs.count() == 0:
        StraightLineModel.objects.create(
            event = event,
            model_type = 'Straight line',
            chisq = results['chisq'],
            BIC = results['BIC'],
            fit_covariance = json.dumps(results['covar'].tolist()),
            intercept = results['coeffs'][0],
            gradient = results['coeffs'][1]
        )

    else:
        slmodel = qs[0]
        slmodel.chisq = results['chisq']
        slmodel.BIC = results['BIC']
        slmodel.fit_covariance = json.dumps(results['covar'].tolist())
        slmodel.intercept = results['coeffs'][0]
        slmodel.gradient = results['coeffs'][1]
        slmodel.save()

    logger.info('Stored straight line model parameters and diagnostics for event ' + event.target.name)

def store_davenportflare_model_parameters(event, results):
    """
    Function to store the parameters from a Davenport flare model fit

    This function stores the first entry in the list of fitted flares
    """

    qs = DavenportFlareModel.objects.filter(
        event=event,
        model_type='Davenport flare'
    )

    if qs.count() == 0:
        DavenportFlareModel.objects.create(
            event=event,
            model_type='Davenport flare',
            t_peak=results['t_peak'],
            t_peak_error=results['t_peak_error'],
            peak_amplitude=results['peak_amplitude'],
            peak_amplitude_error=results['peak_amplitude_error'],
            t_FWHM=results['t_FWHM'],
            t_FWHM_error=results['t_FWHM_error'],
            chisq=results['chisq'],
            BIC=results['BIC']
        )

    else:
        flare = qs[0]
        flare.t_peak = results['t_peak']
        flare.t_peak_error = results['t_peak_error']
        flare.peak_amplitude = results['peak_amplitude']
        flare.peak_amplitude_error = results['peak_amplitude_error']
        flare.t_FWHM = results['t_FWHM']
        flare.t_FWHM_error = results['t_FWHM_error']
        flare.chisq = results['chisq']
        flare.BIC = results['BIC']
        flare.save()

    logger.info('Stored Davenport flare model parameters for event ' + event.target.name)

def store_pitkinflare_model_parameters(event, results):
    """
    Function to store the parameters from a Pitkin flare model fit

    This function stores the first entry in the list of fitted flares
    """

    qs = PitkinFlareModel.objects.filter(
        event=event,
        model_type='Pitkin flare'
    )

    if qs.count() == 0:
        PitkinFlareModel.objects.create(
            event=event,
            model_type='Pitkin flare',
            t_peak=results['t_peak'],
            t_peak_error=results['t_peak_error'],
            peak_amplitude=results['peak_amplitude'],
            peak_amplitude_error=results['peak_amplitude_error'],
            tau_gaussian_rise=results['tau_gaussian_rise'],
            tau_gaussian_rise_error=results['tau_gaussian_rise_error'],
            tau_exponential_decay=results['tau_exponential_decay'],
            tau_exponential_decay_error=results['tau_exponential_decay_error'],
            chisq=results['chisq'],
            BIC=results['BIC']
        )

    else:
        flare = qs[0]
        flare.t_peak = results['t_peak']
        flare.t_peak_error = results['t_peak_error']
        flare.peak_amplitude = results['amplitude']
        flare.peak_amplitude_error = results['amplitude_error']
        flare.tau_gaussian_rise = results['tau_gaussian_rise']
        flare.tau_gaussian_rise_error = results['tau_gaussian_rise_error']
        flare.tau_exponential_decay = results['tau_exponential_decay']
        flare.tau_exponential_decay_error = results['tau_exponential_decay_error']
        flare.chisq = results['chisq']
        flare.BIC = results['BIC']
        flare.save()

    logger.info('Stored Pitkin flare model parameters for event ' + event.target.name)
