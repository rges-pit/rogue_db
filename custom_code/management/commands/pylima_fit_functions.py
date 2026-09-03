from custom_code.management.commands import data_utils
import logging
import numpy as np

from pyLIMA import event
from pyLIMA import telescopes
from pyLIMA import toolbox
from pyLIMA.fits import TRF_fit
from pyLIMA.fits import stats
from pyLIMA.models import PSPL_model, FSPL_model
from pyLIMA.outputs import pyLIMA_plots

from astropy import units as unit

logger = logging.getLogger(__name__)

def run_fit(lcevent, verbose=False):
    """
    Function to perform a microlensing model fit to timeseries photometry.

    Parameters:
        lcevent   (Lightcurve) Event object as opposed to the pyLIMA model event object
        cores integer, optional number of processing cores to use
    """

    logger.info('Starting to model most recent event for source ' + lcevent.target.name)

    # Retrieve timeseries photometry from the DB
    datasets = data_utils.get_reduced_data(lcevent)

    # Fit configuration
    use_boundaries = True

    # Initialize the new event to be fitted:
    current_event = event.Event(ra=lcevent.target.ra, dec=lcevent.target.dec)
    current_event.name = lcevent.target.name

    # Using the lightcurves stored in the TOM for this target,
    # create a list of PyLIMA telescopes, and associate them with the event:
    tel_list = pylima_telescopes_from_datasets(datasets, emag_limit=None)
    for tel in tel_list:
        current_event.telescopes.append(tel)

    # Exception handling here because pyLIMA does its own weeding of poor data from the
    # lightcurves.  Occasionally this leads to all data in a lightcurve being rejected,
    # and pyLIMA will crash if you feed it an empty lightcurve
    # try:
    # The above function imposes a priority order on the list of lightcurves to model,
    # so the reference dataset will always be the first one
    current_event.find_survey('Tel_0')
    current_event.check_event()

    # MODEL 1: PSPL model without parallax
    pspl = PSPL_model.PSPLmodel(current_event, parallax=['None', 0.],
                                blend_flux_parameter='ftotal')
    pspl.define_model_parameters()
    pspl_model_fit = TRF_fit.TRFfit(pspl, loss_function='soft_l1')

    if use_boundaries:
        delta_t0 = 10.
        default_t0_lower = pspl_model_fit.fit_parameters["t0"][1][0]
        default_t0_upper = pspl_model_fit.fit_parameters["t0"][1][1]
        pspl_model_fit.fit_parameters["t0"][1] = [default_t0_lower, default_t0_upper + delta_t0]
        pspl_model_fit.fit_parameters["tE"][1] = [1., 1000.]
        pspl_model_fit.fit_parameters["u0"][1] = [0.0, 2.0]
        if verbose: logger.info('PSPL fit boundaries: t0: '
                                + repr(pspl_model_fit.fit_parameters["t0"][1])
                                + ' tE: ' + repr(pspl_model_fit.fit_parameters["tE"][1])
                                + ' u0: ' + repr(pspl_model_fit.fit_parameters["u0"][1]))

    pspl_model_fit.fit()
    pspl_model_params = gather_model_parameters(current_event, pspl_model_fit, verbose)
    if verbose: logger.info('PSPL fitted parameters ' + repr(pspl_model_params))

    # Evaluate the quality of the best-available model.
    # If the fitted values of key parameters are at the boundaries of then they are considered to
    # be unreliable, and the fit parameters are reset to nan
    pspl_model_params = evaluate_model(pspl_model_params)
    if verbose: logger.info('PSPL evaluated parameters ' + repr(pspl_model_params))

    # MODEL 2: FSPL model without parallax
    fspl = FSPL_model.FSPLmodel(current_event, parallax=['None', 0.],
                                 blend_flux_parameter='ftotal')
    fspl.define_model_parameters()
    fspl_model_fit = TRF_fit.TRFfit(fspl, loss_function='soft_l1')

    if use_boundaries:
        fspl_model_fit.fit_parameters["t0"][1] = [default_t0_lower, default_t0_upper + delta_t0]
        fspl_model_fit.fit_parameters["tE"][1] = [1., 1000.]
        fspl_model_fit.fit_parameters["u0"][1] = [0.0, 2.0]
        fspl_model_fit.fit_parameters["rho"][1] = [0.0, 0.5]
        if verbose: logger.info('FSPL model fit boundaries: t0: '
                                + repr(fspl_model_fit.fit_parameters["t0"][1])
                                + ' tE: ' + repr(fspl_model_fit.fit_parameters["tE"][1])
                                + ' u0: ' + repr(fspl_model_fit.fit_parameters["u0"][1])
                                + ' rho: ' + repr(fspl_model_fit.fit_parameters["rho"][1])
                                )
    fspl_model_fit.fit()
    fspl_model_params = gather_model_parameters(current_event, fspl_model_fit, verbose)
    # default null as in the former implementation
    # model2_params['blend_magnitude'] = np.nan
    if verbose: logger.info('FSPL fitted parameters ' + repr(fspl_model_params))

    # Evaluate the quality of this model
    fspl_model_params = evaluate_model(fspl_model_params)
    if verbose: logger.info('FSPL evaluated parameters ' + repr(fspl_model_params))

    # Decide which fit to accept based on the fitted chi2 in each case.
    # Ordinarily, model1 (with blending, parallax) should produce a lower chi2 because it has more parameters.
    # This test is designed to require evidence that these extra parameters are justified.
    # It should also catch cases where for some reason this fit fails, and the simpler model 2
    # (no blending or parallax) is more reliable.
    # This delta_chi2 will be positive if model 1 is a better fit than model 2.
    # The threshold is calculated assuming a 3-sigma distribution.
    delta_chi2 = fspl_model_params['chi2'] - pspl_model_params['chi2']
    if verbose: logger.info('FITTOOLS: Model 1 chi2 = ' + str(pspl_model_params['chi2']) \
                            + ', model 2 chi2 = ' + str(fspl_model_params['chi2']) \
                            + ', delta_chi2 = ' + str(delta_chi2))
    if delta_chi2 > 0.0:
        best_model = pspl_model_params
        if verbose: logger.info('Using PSPL as best-fit model')
    else:
        best_model = fspl_model_params
        if verbose: logger.info('Using FSPL as best-fit model')

    # Generate the model lightcurve timeseries with the fitted parameters
    if not np.isnan(best_model['tE']):
        model_telescope = generate_model_lightcurve(current_event, best_model, verbose)
        if verbose: logger.info('Generated model lightcurve')
    else:
        model_telescope = None
        if verbose: logger.info('Cannot generate model lightcurve')

    return {
        'best_model': best_model,
        'pspl': pspl_model_params,
        'fspl': fspl_model_params,
        'model_telescope': model_telescope
    }

def pylima_telescopes_from_datasets(datasets, emag_limit=None):
    """Function to convert the dictionary of datasets retrieved from MOP of the lightcurves for this object,
    and convert them into PyLIMA Telescope objects.
    This function returns a list of Telescope objects containing the lightcurve data, applying an
    order of preference, so that prioritized datasets occur at the start of the list.
    """

    # Sort the available datasets into order, giving preference to main survey datasets
    priority_order = ['I', 'ip', 'G', 'i_ZTF', 'r_ZTF', 'R', 'g_ZTF', 'gp']

    dataset_order = []
    for name in priority_order:
        for dataset_id in datasets.keys():
            if name in dataset_id and dataset_id not in dataset_order:
                dataset_order.append(dataset_id)

    for name in datasets.keys():
        if name not in dataset_order:
            dataset_order.append(name)

    # Loop over all available datasets and create a telescope object for each one
    tel_list = []
    for idx, name in enumerate(dataset_order):
        photometry = datasets[name]

        # Enabling optional filtering for datapoints of low photometric precision
        if emag_limit:

            mask = (np.abs(photometry[:, -2].astype(float)) < emag_limit)

        else:

            mask = (np.abs(photometry[:, -2].astype(float)) < 99.0)

        lightcurve = photometry[mask].astype(float)

        # Treating all sites as ground-based without coordinates
        tel = telescopes.Telescope(name='Tel_'+str(idx), camera_filter=name,
                                         lightcurve=photometry[mask],
                                         lightcurve_names=['time', 'mag', 'err_mag'],
                                         lightcurve_units=['JD', 'mag', 'err_mag'])
        tel_list.append(tel)

    return tel_list

def gather_model_parameters(pevent, model_fit, verbose):
    """
    Function to gather the parameters of a PyLIMA fitted model into a dictionary for easier handling.
    """

    # PyLIMA model objects store the fitted values of the model parameters in the fit_results attribute,
    # which is a list of the values pertaining to the model used for the fit.  Since this model can have a
    # variable number of parameters depending on which type of model is used, we use the fit object's built-in
    # list of key indices
    param_keys = list(model_fit.fit_parameters.keys())

    model_params = {}

    for i, key in enumerate(param_keys):
        if key in ['t0' 'tE']:
            ndp = 3
        else:
            ndp = 5
        model_params[key] = np.around(model_fit.fit_results["best_model"][i], ndp)
        model_params[key+'_error'] = np.around(np.sqrt(model_fit.fit_results["covariance_matrix"][i,i]), ndp)

    # model_params['chi2'] = np.around(model_fit.fit_results["best_model"][-1], 3)
    # Reporting actual chi2 instead value of the loss function
    (chi2, pyLIMA_parameters) = model_fit.model_chi2(model_fit.fit_results["best_model"])
    model_params['chi2'] = np.around(chi2, 3)

    # If the model did not include parallax, zero those parameters
    if 'piEN' not in param_keys:
        model_params['piEN'] = 0.0
        model_params['piEN_error'] = 0.0
        model_params['piEE'] = 0.0
        model_params['piEE_error'] = 0.0

    # Calculate the reduced chi2
    ndata = 0
    for i,tel in enumerate(pevent.telescopes):
        ndata += len(tel.lightcurve)
    model_params['red_chi2'] = np.around(model_params['chi2'] / float(ndata - len(param_keys)),3)

    # Retrieve the flux parameters, converting from PyLIMA's key nomenclature to MOPs
    # Fetch the source flux
    try:
        source_flux = model_params['fsource_Tel_0']
        source_flux_error = model_params['fsource_Tel_0_error']
        model_params['source_magnitude'] = np.around(flux_to_mag(source_flux), 3)

        source_mag_error = fluxerror_to_magerror(model_params['fsource_Tel_0'],
                                  model_params['fsource_Tel_0_error'])
        model_params['source_mag_error'] = np.around(source_mag_error, 3)
    except:
        model_params['source_magnitude'] = np.nan
        model_params['source_mag_error'] = np.nan
    if verbose: logger.info('FITTOOLS: source flux ' + str(source_flux) + '+/-' + str(source_flux_error))
    if verbose: logger.info(
        'FITTOOLS: source mag ' + str(model_params['source_magnitude'])
        + '+/-' + str(model_params['source_mag_error'])
    )

    # Handle blend flux, computed from ftotal
    try:
        total_flux = model_params['ftotal_Tel_0']
        total_flux_error = model_params['ftotal_Tel_0_error']
        blend_flux = total_flux - source_flux
        model_params['blend_magnitude'] = np.around(flux_to_mag(blend_flux), 3)

        blend_flux_error = np.sqrt(
            total_flux_error * total_flux_error
            + source_flux_error * source_flux_error
        )
        model_params['blend_mag_error'] = np.around(
            fluxerror_to_magerror(blend_flux,
                                  blend_flux_error),
            3)
    except:
        model_params['blend_magnitude'] = get_zeropoint()
        model_params['blend_mag_error'] = 0.0

    # Occasionally fits with negative blend flux are possible
    if blend_flux < 0.0:
        blend_flux = 0.0
        blend_flux_error = 0.0
        model_params['blend_magnitude'] = get_zeropoint()
        model_params['blend_mag_error'] = 0.0

    if verbose: logger.info('FITTOOLS: blend flux ' + str(blend_flux) + '+/-' + str(blend_flux_error))
    if verbose: logger.info(
        'FITTOOLS: blend mag ' + str(model_params['blend_magnitude'])
        + '+/-' + str(model_params['blend_mag_error'])
    )

    # If the model fitted contains valid entries for both source and blend flux,
    # use these to calculate the baseline magnitude.  Otherwise, use the source magnitude
    if not np.isnan(model_params['source_magnitude']) \
           and not np.isnan(model_params['blend_magnitude']):
        baseline_flux = source_flux + blend_flux
        baseline_flux_error = np.sqrt(
            source_flux_error ** 2 + blend_flux_error ** 2
            + source_flux_error * blend_flux_error
        )
        model_params['baseline_magnitude'] = np.around(flux_to_mag(baseline_flux), 3)
        model_params['baseline_mag_error'] = np.around(fluxerror_to_magerror(baseline_flux, baseline_flux_error), 3)
    else:
        model_params['baseline_magnitude'] = model_params['source_magnitude']
        model_params['baseline_mag_error'] = model_params['source_mag_error']
    if verbose: logger.info(
        'FITTOOLS: baseline mag ' + str(model_params['baseline_magnitude'])
        + '+/-' + str(model_params['baseline_mag_error'])
    )

    model_params['fit_covariance'] = model_fit.fit_results["covariance_matrix"]

    model_params['fit_parameters'] = model_fit.fit_parameters

    # Calculate fit statistics
    # The model_fit.model_residuals returns photometric and astrometric residuals as a dictionary
    # while the photometric residuals provides a list of arrays consisting of the
    # photometric residuals, photometric errors, and error_flux
    try:
        res = model_fit.model_residuals(model_fit.fit_results['best_model'])
        sw_test = stats.normal_Shapiro_Wilk(
            (np.ravel(res[0]['photometry'][0]) / np.ravel(res[1]['photometry'][0])))
        model_params['sw_test'] = np.around(sw_test[0],3)
        ad_test = stats.normal_Anderson_Darling(
            (np.ravel(res[0]['photometry'][0]) / np.ravel(res[1]['photometry'][0])))
        model_params['ad_test'] = np.around(ad_test[0],3)
        ks_test = stats.normal_Kolmogorov_Smirnov(
            (np.ravel(res[0]['photometry'][0]) / np.ravel(res[1]['photometry'][0])))
        model_params['ks_test'] = np.around(ks_test[0],3)
        model_params['chi2_dof'] = np.sum((np.ravel(res[0]['photometry'][0]) / np.ravel(res[1]['photometry'][0])) ** 2) / (
                len(np.ravel(res[0]['photometry'][0])) - 5)
    except:
        model_params['sw_test'] = np.nan
        model_params['ad_test'] = np.nan
        model_params['ks_test'] = np.nan
        model_params['chi2_dof'] = np.nan

    return model_params

def evaluate_model(best_model, verbose=False):
    """Function to evaluate the overall quality of the fitted model.
    The numerical noise threshold implicitly modified the permitted minimum u0 to its value.
    """

    epsilon_numerical_noise = 1e-5
    u0_epsilon = 1e-20

    test1 = np.abs(best_model['fit_parameters']["u0"][1][0] - best_model['u0'])
    test2 = np.abs(best_model['fit_parameters']["u0"][1][1] - best_model['u0'])
    test3 = np.abs(best_model['fit_parameters']["tE"][1][0] - best_model['tE'])
    test4 = np.abs(best_model['fit_parameters']["tE"][1][1] - best_model['tE'])

    if verbose:
        logger.info('FITTOOLS Evaluating model fit:')
        logger.info('Test 1 value='+str(test1)+' criterion >'+str(u0_epsilon))
        logger.info('Test 2 value='+str(test2)+' criterion >'+str(u0_epsilon))
        logger.info('Test 3 value='+str(test3)+' criterion >'+str(epsilon_numerical_noise))
        logger.info('Test 4 value='+str(test3)+' criterion >'+str(epsilon_numerical_noise))

    # The u0 constraints have been removed here after some experimentation because
    # they were found to disallow valid fits for models with low u0 or apparent low u0
    # for models pre-peak.
    #if test1 < u0_epsilon or \
    #    test2 < u0_epsilon or \
    #    test3 < epsilon_numerical_noise or \
    #    test4 < epsilon_numerical_noise:
    if test3 < epsilon_numerical_noise or \
        test4 < epsilon_numerical_noise:
        for key in ['t0', 'u0', 'tE', 'chi2']:
            best_model[key] = np.nan

        if verbose:
            logger.info('FITTOOLS model failed evaluation')

    return best_model

def test_quality_of_model_fit(model_params):
    """Function to evaluate whether the initial model fit indicates a low degree of
    blend flux.  If so, this criterion is used to determine whether to attempt
    a second model fit without blending"""

    fit_no_blend = False

    cov_fit = model_params['fit_covariance']

    if (np.abs(model_params['blend_magnitude']) < 3.0 * cov_fit[4, 4] ** 0.5) or\
            (np.abs(model_params['source_magnitude']) < 3.0 * cov_fit[3, 3] ** 0.5) or\
            (np.abs(model_params['tE']) < 3. * cov_fit[2, 2] ** 0.5):

        fit_no_blend = True

    return fit_no_blend

def generate_model_lightcurve(pevent, model_params, verbose):
    """Function to generate a photometric timeseries corresponding to the given model parameters"""

    pyLIMA_plots.list_of_fake_telescopes = []

    # This doesn't include parallax right now, since none of the fitted models do either yet
    pspl = PSPL_model.PSPLmodel(pevent, parallax=['None', 0.], blend_flux_parameter='ftotal')

    params = []
    parameters = ['t0', 'u0', 'tE']
    for key in parameters:
        value = model_params[key]
        params.append(value)
    source_flux = mag_to_flux(model_params['source_magnitude'])
    params.append(source_flux)
    blend_flux = mag_to_flux(model_params['blend_magnitude'])
    params.append(source_flux+blend_flux)
    if verbose: logger.info('GENERATE LC parameter set: ' + repr(params))

    pyLIMA_parameters = pspl.compute_pyLIMA_parameters(params)

    model_telescope = pyLIMA_plots.create_telescopes_to_plot_model(pspl, pyLIMA_parameters)[0]

    flux_model = pspl.compute_the_microlensing_model(model_telescope, pyLIMA_parameters)['photometry']

    magnitude = toolbox.brightness_transformation.flux_to_magnitude(flux_model)

    model_telescope.lightcurve["mag"] = magnitude * unit.mag

    mask = ~np.isnan(magnitude)
    model_telescope.lightcurve = model_telescope.lightcurve[mask]

    return model_telescope

def get_zeropoint():
    "Magnitude zeropoint equivalent to 1 count of flux; must be the same as used by pyLIMA"
    return 27.4

def chi2(params, fit):

    chi2 = np.sum(fit.residuals_LM(params)**2)
    return chi2


def flux_to_mag(flux):

    ZP_pyLIMA = get_zeropoint()
    magnitude = ZP_pyLIMA - 2.5 * np.log10(flux)
    return magnitude

def fluxerror_to_magerror(flux, flux_error):

    mag_err = (2.5 / np.log(10.0)) * flux_error / flux
    return mag_err

def mag_to_flux(mag):
    """Zeropoint taken from PyLIMA.toolbox.brightness_transformation"""

    ZP_pyLIMA = get_zeropoint()
    flux = 10**((mag - ZP_pyLIMA) / -2.5)

    return flux
