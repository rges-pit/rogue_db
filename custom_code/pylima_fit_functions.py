from custom_code.management.commands import data_utils
from custom_code import statistics
import logging
import numpy as np

from pyLIMA import event
from pyLIMA import telescopes
from pyLIMA import toolbox
from pyLIMA.fits import TRF_fit, MCMC_fit
from pyLIMA.fits import stats
from pyLIMA.models import PSPL_model, FSPL_model
from pyLIMA.outputs import pyLIMA_plots

from astropy import units as unit

logger = logging.getLogger(__name__)

def run_fit(lcevent, bandpass=None, verbose=False):
    """
    Function to perform a microlensing model fit to timeseries photometry.

    Parameters:
        lcevent   (Lightcurve) Event object as opposed to the pyLIMA model event object
    """

    logger.info('Starting to model most recent event for source ' + lcevent.target.name)

    # Retrieve timeseries photometry from the DB
    datasets = data_utils.get_reduced_data(lcevent, bandpass=bandpass)

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
    set_parameter_boundaries(lcevent, pspl_model_fit, verbose=True)
    pspl_model_fit.fit()

    pspl_model_params = gather_model_parameters(current_event, pspl_model_fit, verbose)
    if verbose: logger.info('PSPL fitted parameters ' + repr(pspl_model_params))

    guess_parameters = pspl_model_fit.fit_results['best_model']
    pspl_mcmc_fit = MCMC_fit.MCMCfit(pspl, MCMC_links=10000)

    pspl_mcmc_fit.model_parameters_guess = guess_parameters[:3]
    pspl_mcmc_fit.fit()

    pspl_model_params = mcmc_parameters(current_event, pspl_model_params, pspl_mcmc_fit)
    if verbose: logger.info('PSPL MCMC parameters ' + repr(pspl_model_params))


    # MODEL 2: FSPL model without parallax
    fspl = FSPL_model.FSPLmodel(current_event, parallax=['None', 0.],
                                 blend_flux_parameter='ftotal')
    fspl.define_model_parameters()
    fspl_model_fit = TRF_fit.TRFfit(fspl, loss_function='soft_l1')
    set_parameter_boundaries(
        lcevent, fspl_model_fit,
        prior_model_params=pspl_model_params, verbose=True
    )
    fspl_model_fit.fit()

    fspl_model_params = gather_model_parameters(current_event, fspl_model_fit, verbose)
    # default null as in the former implementation
    # model2_params['blend_magnitude'] = np.nan
    if verbose: logger.info('FSPL fitted parameters ' + repr(fspl_model_params))

    guess_parameters = fspl_model_fit.fit_results['best_model']

    fspl_mcmc_fit = MCMC_fit.MCMCfit(fspl)

    fspl_mcmc_fit.model_parameters_guess = guess_parameters[:4]
    fspl_mcmc_fit.fit()

    fspl_model_params = mcmc_parameters(current_event, fspl_model_params, fspl_mcmc_fit)
    if verbose: logger.info('FSPL MCMC parameters ' + repr(fspl_model_params))

    # Decide which fit to accept based on the fitted chi2 in each case.
    # Ordinarily, model1 (with blending, parallax) should produce a lower chi2 because it has more parameters.
    # This test is designed to require evidence that these extra parameters are justified.
    # It should also catch cases where for some reason this fit fails, and the simpler model 2
    # (no blending or parallax) is more reliable.
    # The threshold is calculated assuming a 3-sigma distribution.
    if len(pspl_model_params) > 0 and len(fspl_model_params):
        delta_chi2 = fspl_model_params['red_chi2'] - pspl_model_params['red_chi2']
        if verbose: logger.info('PSPL red chi2 = ' + str(pspl_model_params['red_chi2']) \
                                + ', FSPL red chi2 = ' + str(fspl_model_params['red_chi2']) \
                                + ', delta_chi2 = ' + str(delta_chi2))
        if delta_chi2 > 0.0:
            best_model = pspl_model_params
            if verbose: logger.info('Using PSPL as best-fit model')
        else:
            best_model = fspl_model_params
            if verbose: logger.info('Using FSPL as best-fit model')
    else:
        best_model = {}

    # Generate the model lightcurve timeseries with the fitted parameters
    if len(pspl_model_params) > 0 and not np.isnan(pspl_model_params['tE']):
        model_telescope_pspl = generate_model_lightcurve(current_event, pspl_model_params, verbose)
        if verbose: logger.info('Generated PSPL model lightcurves')
    else:
        model_telescope_pspl = None
        if verbose: logger.info('Cannot generate PSPL model lightcurves')

    if len(fspl_model_params) > 0 and not np.isnan(fspl_model_params['tE']):
        model_telescope_fspl = generate_model_lightcurve(current_event, fspl_model_params, verbose)
        if verbose: logger.info('Generated FSPL model lightcurves')
    else:
        model_telescope_fspl = None
        if verbose: logger.info('Cannot generate FSPL model lightcurves')

    return {
        'best_model': best_model,
        'pspl': pspl_model_params,
        'fspl': fspl_model_params,
        'model_telescope_pspl': model_telescope_pspl,
        'model_telescope_fspl': model_telescope_fspl
    }

def set_parameter_boundaries(lcevent, mulens_model_fit, verbose=False,
                             use_boundaries=True, prior_model_params={}):
    """
    Function to establish the initial guess and parameter boundaries appropriate to an event

    Parameters:
        lcevent             Event object
        mulens_model_fit    pyLIMA model fit object

    Returns:
        mulens_model_fit    pyLIMA model fit object
    """

    # Estimate initial-guess parameters based on the Target's parameters,
    # which are set from the alert information
    if len(prior_model_params) == 0 and lcevent.target.t0:
        mulens_model_fit.model_parameters_guess = [
            lcevent.target.t0,
            lcevent.target.u0,
            lcevent.target.tE
        ]
    elif len(prior_model_params) > 0:
        mulens_model_fit.model_parameters_guess = [
            prior_model_params['t0'],
            prior_model_params['u0'],
            prior_model_params['tE']
        ]
    else:
        mulens_model_fit.model_parameters_guess = [ 0.0, 0.0, 0.0 ]

    if mulens_model_fit.model.model_type() == 'FSPL':
        mulens_model_fit.model_parameters_guess.append(0.0)

    if verbose: logger.info(mulens_model_fit.model.model_type() + ' fit initial guess: '
                            + repr(mulens_model_fit.model_parameters_guess))

    # Establish boundaries for the optimization process
    if use_boundaries:
        if lcevent.target.t0:
            trange = max(2.0 * lcevent.target.tE, 2.0)
            mulens_model_fit.fit_parameters["t0"][1] = [
                lcevent.target.t0 - trange/2.0,
                lcevent.target.t0 + trange/2.0,
            ]
        else:
            mulens_model_fit.fit_parameters["t0"][1] = [0.0, 10.0]
        mulens_model_fit.fit_parameters["tE"][1] = [0.0, 100.]
        mulens_model_fit.fit_parameters["u0"][1] = [-2.0, 2.0]

        if mulens_model_fit.model.model_type() == 'FSPL':
            mulens_model_fit.fit_parameters["rho"][1] = [0.0, 0.5]

        if verbose:
            if mulens_model_fit.model.model_type() == 'PSPL':
                logger.info(mulens_model_fit.model.model_type() + ' fit boundaries: t0: '
                                + repr(mulens_model_fit.fit_parameters["t0"][1])
                                + ' tE: ' + repr(mulens_model_fit.fit_parameters["tE"][1])
                                + ' u0: ' + repr(mulens_model_fit.fit_parameters["u0"][1]))
            elif mulens_model_fit.model.model_type() == 'FSPL':
                logger.info(mulens_model_fit.model.model_type() + ' fit boundaries: t0: '
                            + repr(mulens_model_fit.fit_parameters["t0"][1])
                            + ' tE: ' + repr(mulens_model_fit.fit_parameters["tE"][1])
                            + ' u0: ' + repr(mulens_model_fit.fit_parameters["u0"][1])
                            + ' rho: ' + repr(mulens_model_fit.fit_parameters["rho"][1])
                            )

    return mulens_model_fit

def pylima_telescopes_from_datasets(datasets, emag_limit=None):
    """Function to convert the dictionary of datasets retrieved from MOP of the lightcurves for this object,
    and convert them into PyLIMA Telescope objects.
    This function returns a list of Telescope objects containing the lightcurve data, applying an
    order of preference, so that prioritized datasets occur at the start of the list.
    """

    # Sort the available datasets into order, giving preference to main survey datasets
    priority_order = ['F146', 'F184', 'F213', 'I', 'ip', 'G', 'i_ZTF', 'r_ZTF', 'R', 'g_ZTF', 'gp']

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
        if name in ['F146', 'F184', 'F213']:
            tel.location = 'Space'
            tel.spacecraft_name = 'L2'
        tel_list.append(tel)

    return tel_list

def calc_magnification(u0, u0_err):

    def calc_A(u0):
        A = (u0 * u0 + 2) / (u0 * np.sqrt(u0 * u0 + 4))
        if np.isinf(A):
            A = 10000.0
        return A

    A = calc_A(u0)
    A_max = calc_A(u0 - u0_err)
    A_min = calc_A(u0 + u0_err)
    A_err = (A_max - A_min) / 2.0

    return A, A_err

def gather_model_parameters(pevent, model_fit, verbose):
    """
    Function to gather the parameters of a PyLIMA TRF fitted model into a dictionary for
    easier handling.
    """
    if 'best_model' in model_fit.fit_results.keys():
        # PyLIMA model objects store the fitted values of the model parameters in the fit_results attribute,
        # which is a list of the values pertaining to the model used for the fit.  Since this model can have a
        # variable number of parameters depending on which type of model is used, we use the fit object's built-in
        # list of key indices
        param_keys = list(model_fit.fit_parameters.keys())

        model_params = {'fit_method': 'TRF'}

        for i, key in enumerate(param_keys):
            if key in ['t0' 'tE']:
                ndp = 3
            else:
                ndp = 5
            model_params[key] = np.around(model_fit.fit_results["best_model"][i], ndp)
            if 'covariance_matrix' in model_fit.fit_results.keys():
                model_params[key+'_error'] = np.around(np.sqrt(model_fit.fit_results["covariance_matrix"][i,i]), ndp)

        model_params['A0'],model_params['A0_error'] = calc_magnification(model_params['u0'], model_params['u0_error'])

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

        # Calculate goodness of fit criteria
        ndata = 0
        for i,tel in enumerate(pevent.telescopes):
            ndata += len(tel.lightcurve)
        model_params['red_chi2'] = np.around(model_params['chi2'] / float(ndata - len(param_keys)),3)
        model_params['BIC'] = model_params['chi2'] + len(param_keys) * np.log(ndata)

        # Retrieve the flux parameters, converting from PyLIMA's key nomenclature to MOPs
        model_params = extract_flux_parameters(model_params)

        # Store parameters
        model_params['fit_covariance'] = model_fit.fit_results["covariance_matrix"]
        model_params['fit_parameters'] = model_fit.fit_parameters

        # Calculate fit statistics
        model_params = calculate_fit_statistics(model_params, model_fit)

    else:
        logger.error('No model best fit results to record')

        model_params = {}

    return model_params

def extract_flux_parameters(model_params):
    """
    Function to extract the source and blend flux parameters and compute uncertainties
    """

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
        source_flux = np.nan
        source_flux_error = np.nan
        model_params['source_magnitude'] = np.nan
        model_params['source_mag_error'] = np.nan
    logger.info('Source flux ' + str(source_flux) + '+/-' + str(source_flux_error))
    logger.info(
        'Source mag ' + str(model_params['source_magnitude'])
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

    logger.info('Blend flux ' + str(blend_flux) + '+/-' + str(blend_flux_error))
    logger.info(
        'Blend mag ' + str(model_params['blend_magnitude'])
        + '+/-' + str(model_params['blend_mag_error'])
    )

    return model_params

def calculate_fit_statistics(model_params, model_fit):
    """
    Calculate fit statistics
    The model_fit.model_residuals returns photometric and astrometric residuals as a dictionary
    while the photometric residuals provides a list of arrays consisting of the
    photometric residuals, photometric errors, and error_flux
    """

    try:
        res = model_fit.model_residuals(model_fit.fit_results['best_model'])
        sw_test = stats.normal_Shapiro_Wilk(
            (np.ravel(res[0]['photometry'][0]) / np.ravel(res[1]['photometry'][0])))
        model_params['sw_test'] = np.around(sw_test[0], 3)
        ad_test = stats.normal_Anderson_Darling(
            (np.ravel(res[0]['photometry'][0]) / np.ravel(res[1]['photometry'][0])))
        model_params['ad_test'] = np.around(ad_test[0], 3)
        ks_test = stats.normal_Kolmogorov_Smirnov(
            (np.ravel(res[0]['photometry'][0]) / np.ravel(res[1]['photometry'][0])))
        model_params['ks_test'] = np.around(ks_test[0], 3)
        model_params['chi2_dof'] = np.sum(
            (np.ravel(res[0]['photometry'][0]) / np.ravel(res[1]['photometry'][0])) ** 2) / (
                                           len(np.ravel(res[0]['photometry'][0])) - 5)
    except:
        model_params['sw_test'] = np.nan
        model_params['ad_test'] = np.nan
        model_params['ks_test'] = np.nan
        model_params['chi2_dof'] = np.nan

    return model_params

def mcmc_parameters(pevent, model_params, mcmc_fit):
    """
    Function to harvest the best-fit model results from a PyLIMA MCMC fit

    This function replaces the best-fit parameter values if the fit converged.
    If not, the TRF best-fit values are used.
    """

    # Robust against missing parameters in the case of an aborted fit
    try:
        # Store parameters
        model_params['fit_parameters'] = mcmc_fit.fit_parameters

        # Derive MCMC samples from the chains
        chains = mcmc_fit.fit_results['MCMC_chains_with_fluxes']
        print('PYLIMA CHAINS: ', chains.shape)
        model_params['samples'] = chains.reshape(-1, chains.shape[2])
        model_params['parameter_labels'] = list(mcmc_fit.fit_parameters.keys())
        model_params['sample_columns'] = [0, 1, 2]
        if 'rho' in mcmc_fit.fit_parameters.keys():
            model_params['labels'].append('rho')
            model_params['sample_columns'].append(3)
        model_params['tau'], model_params['tau_threshold'] = statistics.calc_tau(chains)

        # Extract best-fit model parameter values
        for i,key in enumerate(mcmc_fit.priors_parameters.keys()):
            model_params[key] = mcmc_fit.fit_results['best_model'][i]
            if 'likelihood' not in key:
                model_params[key + '_error'] = 0.5 * (np.percentile(model_params['samples'][:, i], 84)
                                              - np.percentile(model_params['samples'][:, i], 16))

        # Calculate peak magnification
        model_params['A0'], model_params['A0_error'] = calc_magnification(model_params['u0'], model_params['u0_error'])

        # Calculate goodness of fit criteria
        ndata = 0
        for i,tel in enumerate(pevent.telescopes):
            ndata += len(tel.lightcurve)
        (chi2, pyLIMA_parameters) = mcmc_fit.model_chi2(mcmc_fit.fit_results["best_model"])
        model_params['chi2'] = np.around(chi2, 3)
        model_params['BIC'] = model_params['chi2'] + len(mcmc_fit.fit_parameters.keys()) * np.log(ndata)

        # Retrieve the flux parameters, converting from PyLIMA's key nomenclature to MOPs
        model_params = extract_flux_parameters(model_params)

        # Calculate fit statistics
        model_params = calculate_fit_statistics(model_params, mcmc_fit)

        # Record fit method
        model_params['fit_method'] = 'MCMC'

    except KeyError:
        logger.warning('MCMC failed')

    return model_params

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

    if len(model_params)> 0:
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

    else:
        logger.error('No model parameters; cannot generate model lightcurve')

        model_telescope = telescopes.Telescope(name='NONE',
                                               camera_filter='I',
                                               pixel_scale=1,
                                               lightcurve=np.empty())

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
    """Magnitude uncertainties are capped at 10mag to avoid inf or NaN"""
    mag_err = (2.5 / np.log(10.0)) * flux_error / flux
    if np.isinf(mag_err):
        mag_err = 10.0

    return mag_err

def mag_to_flux(mag):
    """Zeropoint taken from PyLIMA.toolbox.brightness_transformation"""

    ZP_pyLIMA = get_zeropoint()
    flux = 10**((mag - ZP_pyLIMA) / -2.5)

    return flux
