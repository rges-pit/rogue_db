from tom_dataproducts.models import PhotometryReducedDatum, ReducedDatum
import numpy as np
import logging
from custom_code.models import MicrolensingModel
from datetime import datetime, timedelta
import pytz
from astropy.time import Time
import json

logger = logging.getLogger(__name__)


def get_reduced_data(mulens):
    """Function to extract the timeseries data from a QuerySet of PhotometryReducedDatums, and
    creates the necessary arrays.
    Also accepts a QuerySet of generic ReducedDatums (lc_model, tabular, etc.) for the same
    target, used to identify pre-existing derived datasets.
    Note that the querysets must be provided separately and not derived directly from a query
    """

    photometry_qs = PhotometryReducedDatum.objects.filter(target__name=mulens.name).order_by("timestamp")

    datasets = {}

    for rd in photometry_qs:
        # Identify different lightcurves from the filter label given
        passband = rd.bandpass
        if passband in datasets.keys():
            lc = datasets[passband]
        else:
            lc = []

        # Append the datapoint to the corresponding dataset
        try:
            lc.append([Time(rd.timestamp).jd, rd.brightness, rd.brightness_error])
        except:
            # Necessary to handle the datapoints where only a limit is available.
            # Skipping these for now
            try:
                lc.append([Time(rd.timestamp).jd, rd.brightness, 1.0])
            except KeyError:
                pass

        datasets[passband] = lc

    # Convert the accumulated lightcurves into numpy arrays:
    for passband, lc in datasets.items():
        datasets[passband] = np.array(lc)

    logger.info('Found ' + str(len(datasets)) + ' datasets')

    return datasets

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

def store_model_parameters(mulens, pylima_results):
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
            setattr(mulens, key, data)
    mulens.save()

    # Store the PSPL and FSPL model fit parameters as MicrolensingModel entries
    for model_category in ['pspl', 'fspl']:
        qs  = MicrolensingModel.objects.filter(
            target=mulens,
            model_type='Microlensing',
            model_category=model_category.upper()
        )

        if qs.count() == 0:
            if model_category == 'pspl':
                rd = MicrolensingModel.objects.create(
                    model_type='Microlensing',
                    model_category=model_category.upper(),
                    target=mulens,
                    t0=pylima_results[model_category]['t0'],
                    t0_error=pylima_results[model_category]['t0_error'],
                    u0=pylima_results[model_category]['u0'],
                    u0_error=pylima_results[model_category]['u0_error'],
                    tE=pylima_results[model_category]['tE'],
                    tE_error=pylima_results[model_category]['tE_error'],
                    piEN=pylima_results[model_category]['piEN'],
                    piEN_error=pylima_results[model_category]['piEN_error'],
                    piEE=pylima_results[model_category]['piEE'],
                    piEE_error=pylima_results[model_category]['piEE_error'],
                    chisq=pylima_results[model_category]['chi2'],
                )
            else:
                rd = MicrolensingModel.objects.create(
                    model_type='Microlensing',
                    model_category=model_category.upper(),
                    target=mulens,
                    t0=pylima_results[model_category]['t0'],
                    t0_error=pylima_results[model_category]['t0_error'],
                    u0=pylima_results[model_category]['u0'],
                    u0_error=pylima_results[model_category]['u0_error'],
                    tE=pylima_results[model_category]['tE'],
                    tE_error=pylima_results[model_category]['tE_error'],
                    piEN=pylima_results[model_category]['piEN'],
                    piEN_error=pylima_results[model_category]['piEN_error'],
                    piEE=pylima_results[model_category]['piEE'],
                    piEE_error=pylima_results[model_category]['piEE_error'],
                    rho=pylima_results[model_category]['rho'],
                    rho_error=pylima_results[model_category]['rho_error'],
                    chisq=pylima_results[model_category]['chi2'],
                )

        else:
            rd = qs[0]
            rd.model_type = 'Microlensing'
            rd.model_category = model_category.upper()
            rd.target = mulens
            rd.t0=pylima_results[model_category]['t0']
            rd.t0_error=pylima_results[model_category]['t0_error']
            rd.u0=pylima_results[model_category]['u0']
            rd.u0_error=pylima_results[model_category]['u0_error']
            rd.tE=pylima_results[model_category]['tE']
            rd.tE_error=pylima_results[model_category]['tE_error']
            rd.piEN=pylima_results[model_category]['piEN']
            rd.piEN_error=pylima_results[model_category]['piEN_error']
            rd.piEE=pylima_results[model_category]['piEE']
            rd.piEE_error=pylima_results[model_category]['piEE_error']
            if model_category == 'fspl':
                rd.rho=pylima_results[model_category]['rho']
                rd.rho_error=pylima_results[model_category]['rho_error']
            rd.chisq=pylima_results[model_category]['chi2']
            rd.save()

    logger.info('Stored model parameters for event ' + mulens.name)