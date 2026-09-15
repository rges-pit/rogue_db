from custom_code.management.commands import data_utils
import logging
from altaipony.fit_flares import fit_flares, make_flare_table, build_baseline
from altaipony.fakeflares import flare_model_davenport2014
from custom_code import utils
import numpy as np

logger = logging.getLogger(__name__)

def run_davenport_flare_fit(lcevent):
    """
    Function to perform a Davenport flare model fit to an Event

    Parameters:
        lcevent   (Lightcurve) Event object

    Returns:
        flare_table  DataFrame  Results from flare model fit
    """

    logger.info('Starting Davenport flare model fit to event for source ' + lcevent.target.name)

    # Retrieve Roman's primary timeseries photometry from the DB
    datasets = data_utils.get_reduced_data(lcevent)
    lightcurve = data_utils.fetch_lightcurve(datasets)

    # Set a cap of a minimum of ten points for a sensible fit
    results = {}
    if len(lightcurve) > 10:
        flux, flux_err = utils.mag_to_flux(lightcurve[:,1], lightcurve[:,2])
        tstarts = [lcevent.start_time]
        tstops = [lcevent.start_time + lcevent.duration]

        # Note: This constraints the model to fit a single flare only
        df = fit_flares(lightcurve[:,0], flux, flux_err, tstarts, tstops,
                   buffer=0.05, max_flares=1, delta_bic=0.0,
                   plot=False, debug_plot=False)

        flare_table = make_flare_table(df, include_group_rows=False)

        flare_model = flare_model_davenport2014(
        df[0]['time'], df[0]['t_peak'], df[0]['fwhm'], df[0]['amplitude']
        )
        baseline = build_baseline(df[0]['time'], df[0]['params'][:5])
        flux_lc = baseline + flare_model

        chi2, bic = calc_goodness_of_flare_fit(df[0]['flux'], df[0]['flux_err'], flux_lc)

        # For the sake of compatibility with the rest of the codebase, distill the results
        # into a dictionary
        results['t_peak'] = flare_table['t_peak'][0]
        results['t_peak_error'] = flare_table['t_peak_err'][0]
        results['peak_amplitude'] = flare_model['amplitude'][0]
        results['peak_amplitude_error'] = flare_model['amplitude_err'][0]
        results['t_FWHM'] = flare_model['fwhm'][0]
        results['t_FWHM_error'] = flare_model['fwhm_err'][0]
        results['chisq'] = chi2
        results['BIC'] = bic

    return results

def calc_goodness_of_flare_fit(flux, flux_err, flux_lc):
    """
    Function to calculate the goodness-of-fit parameters chisq, BIC from the
    results of an Altaipony fit

    Parameters:
        flux        array   Real data flux values
        flux_err    array   Real data flux uncertainties
        flux_lc     array   Flare model lightcurve

    Returns:
        chi2       float   Chi squared
        bic         float   Bayesian Information Criteria
    """

    # Generate the model lightcurve, following Altaipony's method, and convert to magnitudes
    model_mag, _, _, _ = utils.flux_to_mag(flux_lc, np.ones(len(flux_lc)))
    data_mag, data_mag_err, _, _ = utils.flux_to_mag(flux, flux_err)

    # Calculate diagnostics
    # Nparam = 3
    chi2 = np.sum((data_mag - model_mag)**2 / (float(len(data_mag)) - 3.0))
    bic = chi2 + 3.0 * np.log(len(data_mag))

    return chi2, bic

def run_pitkin_flare_model_fit(lcevent):
    """
    Function to perform a Pitkin flare model fit to an Event

    Parameters:
        lcevent   (Lightcurve) Event object

    Returns:
        best_fit    array     Parameters of the best-fit flare model
    """

    logger.info('Starting Pitkin flare model fit to event for source ' + lcevent.target.name)

    # Retrieve Roman's primary timeseries photometry from the DB.  Convert to flux
    datasets = data_utils.get_reduced_data(lcevent)
    lightcurve = data_utils.fetch_lightcurve(datasets)
    flux, flux_err = utils.mag_to_flux(lightcurve[:,1], lightcurve[:,2])

    # Starting parameters for MCMC fit, baseline paramters
    nwalkers = 50
    n_steps = 3000
    discard = 500   # Number of steps of burn-in
    thinning_factor = 10 # Thinning factor for MCMC chains
    baseline_guess = [np.median(flux)]
    flare_guess = [
        lcevent.start_time + (lcevent.duration/2.0), # t_peak
        200.0,                                       # peak_amplitude
        0.2,                                         # tau_gaussian_rise
        0.5                                          # tau_exponential_decay
    ]
    guess = baseline_guess + flare_guess
    ndim = len(guess)
    start_position = np.array(guess) + 1e-5 * np.random.randn(max(2 * ndim, nwalkers), ndim)

    # Boundary conditions for the fit
    t_bounds = [lcevent.start_time, lcevent.start_time + lcevent.duration]
    peak_bounds = [0.0001, 100000.0]
    tau_gaussian_rise_bounds = [0.0000001, 1.5]
    tau_exponential_decay_bounds = [0.0000001, 3.0]

    # Run MCMC
    sampler = emcee.EnsembleSampler(len(start_position), ndim, calc_log_posterior,
                                    args=(
                                        lightcurve[:,0], flux, flux_err,
                                        t_bounds, peak_bounds,
                                        tau_gaussian_rise_bounds, tau_exponential_decay_bounds
                                    )
                                    )


    sampler.run_mcmc(start_position, n_steps, progress=True)
    samples = sampler.get_chain(discard=discard, thin=thinning_factor, flat=True)
    best_fit = np.median(samples, axis=0)

    # Generate a model lightcurve with these parameters and
    # calculate the chisq and BIC
    flare_model = model_pitkin_flare_lightcurve(lightcurve[:,0], best_fit)
    baseline = np.zeros(len(lightcurve[:,0]))
    baseline.fill(params[0])
    flux_lc = baseline + flare_model

    chi2, bic = calc_goodness_of_flare_fit(flux, flux_err, flux_lc)

    # Build results dictionary for consistency
    # [baseline_flux, t, flux, peak, fwhm, tau_gaussian_rise, tau_exponential_decay]
    results = {
        't_peak': best_fit[1],
        't_peak_error': 0.0,
        'peak_amplitude': best_fit[3],
        'peak_amplitude_error': 0.0,
        'tau_gaussian_rise': best_fit[4],
        'tau_gaussian_rise_error': 0.0,
        'tau_exponential_decay': best_fit[5],
        'tau_exponential_decay_error': 0.0,
        'chisq': chi2,
        'BIC': bic
    }

    return results

def calc_log_posterior(
        params, time, flux, flux_err, t_bounds, peak_bounds,
        tau_gaussian_rise_bounds, tau_exponential_decay_bounds
):
    """
    Function to compute the log(posterior) for the distribution where
    posterior = log(prior) + log(likelihood)

    This function is passed to the MCMC fit and evaluated at each step in the chain

    Parameters:
        params      dict    Model parameter set
        time        array   Timestamps of observations
        flux        array   Flux measurements
        flux_err    array   Flux uncertainties
        t_bounds    array   Boundary conditions for time
        peak_bounds array   Boundary conditions for peak flux
        tau_gaussian_rise_bounds array Boundary conditions for tau_gaussian_rise parameter
        tau_exponential_decay_bounds array Boundary conditions for tau_exponential_decay

    Returns:
        log_posterior float  Log value of posterior distribution for given parameter set
    """

    # Verify all passed arrays have the same dimensions
    if not (len(time) == len(flux) == len(flux_err)):
        raise ValueError("Mismatch in length of time, flux, and flux_err arrays")
    if len(params) < 7:
        raise ValueError("params must include at least 5 baseline values")

    if np.any(~np.isfinite(params)):
        return -np.inf

    lp = calc_log_prior(params, t_bounds, peak_bounds,
        tau_gaussian_rise_bounds, tau_exponential_decay_bounds)
    if not np.isfinite(lp):
        return -np.inf

    try:
        ll = calc_log_likelihood(params, time, flux, flux_err)
    except Exception as e:
        print('Error in evaluation of likelihood, ' + repr(e))
        return -np.inf

    return lp + ll

def calc_log_prior(params, t_bounds, peak_bounds,
        tau_gaussian_rise_bounds, tau_exponential_decay_bounds):
    """
    The prior function requires that the flare parameter values remain within the
    boundaries set by the user.

    Parameters
        params      array           Model parameters (baseline flux parameters + flare parameters)
        t_bounds    list of floats  Boundary conditions for t_peak
        peak_bounds list of floats  Boundary conditions for peak flux
        tau_gaussian_rise_bounds list of floats  Boundary conditions for tau_gaussian_rise
        tau_exponential_decay_bounds list of floats Boundary conditions for tau_exponential_decay

    Returns
        log_prior   float   0 if within bounds, -inf otherwise
    """

    # Verify input parameters and boundary arrays
    if len(params) < 6:
        raise ValueError("params array must contain 7 parameter values")

    if len(t_bounds) != 2 or len(peak_bounds) != 2 \
        or len(tau_gaussian_rise_bounds) != 2 or len(tau_exponential_decay_bounds):
        raise ValueError('Boundary conditions must contain a minimum and maximum value')

    # Check parameter values are within all boundary conditions and finite
    # params = [baseline_flux, t, flux, peak, fwhm, tau_gaussian_rise, tau_exponential_decay]
    if not np.isfinite(params).all():
        return -np.inf

    if not (t_bounds[0] < params[1] < t_bounds[1]):
        return -np.inf

    if not (peak_bounds[0] < params[3] < peak_bounds[1]):
        return -np.inf

    if not (tau_gaussian_rise_bounds[0] < params[5] < tau_gaussian_rise_bounds[1]):
        return -np.inf

    if not (tau_exponential_decay_bounds[0] < params[6] < tau_exponential_decay_bounds[1]):
        return -np.inf

    return 0.0

def calc_log_likelihood(params, time, flux, flux_err):
    """
    Function to return the Gaussian log likelihood of a (time, flux, flux_err) parameter set

    Parameters
        params  array   Model parameters (baseline flux parameters + flare parameters)
        time    array   Timestamps of datapoints
        flux    array   Timeseries flux measurements
        flux_err array  Timeseries flux uncertainties

    Returns
        Log likelihood float Likelihood of the (time, flux, flux_err) value
    """

    # Verify input is sensible
    if not (len(time) == len(flux) == len(flux_err)):
        raise ValueError("Mismatch between input time, flux and flux_err array lengths")

    if len(time) == 0:
        raise ValueError("Input arrays must not be empty")

    if np.any(~np.isfinite(time)) or np.any(~np.isfinite(flux)) or np.any(~np.isfinite(flux_err)):
        raise ValueError("Input arrays contain NaN or inf")

    # Generate a model lightcurve
    model_lc = model_pitkin_flare_lightcurve(time, params)

    # Calculate the likelihood
    with np.errstate(divide="ignore", invalid="ignore"):
        chi2 = ((flux - model_lc) / flux_err) ** 2
        log_term = np.log(2 * np.pi * flux_err ** 2)
        chi2[~np.isfinite(chi2)] = 1e10  # large penalty
        log_term[~np.isfinite(log_term)] = 1e10

    return -0.5 * np.sum(chi2 + log_term)

def model_pitkin_flare_lightcurve(time, params):
    """
    Function to return a timeseries flux array of a Pitkin flare, based on the input
    timestamps and flare model parameters

    Parameters
        time    array  Timestamps
        params  array  Model parameters (baseline flux parameters + flare parameters)
                [baseline_flux, t, flux, peak, fwhm, tau_gaussian_rise, tau_exponential_decay]
    Returns
        model_lc   array    Timeseries model flux values
    """

    model_lc = np.zeros(len(time))

    # Set the peak flux amplitude
    model_lc[time == params[1]] = params[3]

    # Set rising lightcurve
    if params[5] > 0:
        model_lc[time < params[1]] = params[3] * np.exp(-(time[time < t0] - params[1]) ** 2 / (2 * float(params[4]) ** 2))

    # Set declining lightcurve
    if params[6] > 0:
        model_lc[time > params[1]] = params[3] * np.exp(-(time[time > params[1]] - params[1]) / float(params[5]))

    return model_lc