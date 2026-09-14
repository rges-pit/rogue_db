from tom_dataproducts.models import PhotometryReducedDatum, ReducedDatum
import numpy as np
import logging
from custom_code.models import PSPLModel, FSPLModel, StraightLineModel, Event, DavenportFlareModel
from datetime import datetime
import pytz
from astropy.time import Time
import json

logger = logging.getLogger(__name__)


def get_reduced_data(event):
    """Function to extract the timeseries data from a QuerySet of PhotometryReducedDatums, and
    creates the necessary arrays.
    Also accepts a QuerySet of generic ReducedDatums (lc_model, tabular, etc.) for the same
    target, used to identify pre-existing derived datasets.
    Note that the querysets must be provided separately and not derived directly from a query
    """

    photometry_qs = PhotometryReducedDatum.objects.filter(target__name=event.target.name).order_by("timestamp")

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

def store_model_lightcurve(mulens, model):
    """Function to store in the TOM the timeseries lightcurve corresponding to a fitted model.
    The input is a model fit object from PyLIMA.

    Note that this function has to be separate from the MicrolensingTarget class because it uses the
    ReducedDatum objects.  Circular imports result if you try to import ReducedDatums from the Target object"""

    tz = pytz.timezone('utc')
    model_time = datetime.utcnow().replace(tzinfo=tz)

    # Extract the model lightcurve timeseries from the PyLIMA fit object
    data = {
        'lc_model_time': model.lightcurve['time'].value.tolist(),
        'lc_model_magnitude': model.lightcurve['mag'].value.tolist()
    }

    # If there is no existing model for this target, create one
    qs = ReducedDatum.objects.filter(target=mulens, data_type='lc_model')
    if qs.count() == 0:
        rd = ReducedDatum.objects.create(
            timestamp=model_time,
            value=data,
            source_name='RogueDB',
            source_location=mulens.name,
            data_type='lc_model',
            target=mulens
        )
        logger.info('Created lightcurve model datum for ' + mulens.name)

    # If there is a pre-existing model, update it
    else:
        rd = qs[0]
        rd.timestamp = model_time
        rd.value = data
        rd.source_name = 'RogueDB'
        rd.source_location = mulens.name
        rd.data_type = 'lc_model'
        rd.target = mulens
        rd.save()
        logger.info('Updated existing lightcurve model datum for ' + mulens.name)

    return mulens

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

def store_straightline_model_parameters(event, results):

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

    # Update the Event itself with the diagnostics from the straight line fit
    Event.objects.filter(pk=event.pk).update(
        frac_below_baseline=results['frac_below_baseline'],
        max_excursion_below_baseline=results['max_excursion_below_baseline'],
    )

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
            t_peak=results['t_peak'][0],
            t_peak_error=results['t_peak_err'][0],
            peak_amplitude=results['amplitude'][0],
            peak_amplitude_error=results['amplitude_err'][0],
            t_FWHM=results['fwhm'][0],
            t_FWHM_error=results['fwhm_err'][0],
            chisq=results['chisq'][0],
            BIC=results['BIC'][0]
        )

    else:
        flare = qs[0]
        flare.t_peak = results['t_peak'][0]
        flare.t_peak_error = results['t_peak_err'][0]
        flare.peak_amplitude = results['amplitude'][0]
        flare.peak_amplitude_error = results['amplitude_err'][0]
        flare.t_FWHM = results['fwhm'][0]
        flare.t_FWHM_error = results['fwhm_err'][0]
        flare.chisq = results['chisq'][0]
        flare.BIC = results['BIC'][0]
        flare.save()

    logger.info('Stored Davenport flare model parameters for event ' + event.target.name)
