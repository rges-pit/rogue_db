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
        chi2        float       Chi-squared value of the fit
        BIC         float       Bayesian Information Criteria of the fit
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
        results = fit_flares(lightcurve[:,0], flux, flux_err, tstarts, tstops,
                   buffer=0.05, max_flares=1, delta_bic=0.0,
                   plot=False, debug_plot=False)

        flare_table = make_flare_table(results, include_group_rows=False)

        chi2, bic = calc_goodness_of_flare_fit(results)
        flare_table['chisq'] = chi2
        flare_table['BIC'] = bic

    return flare_table

def calc_goodness_of_flare_fit(results):
    """
    Function to calculate the goodness-of-fit parameters chisq, BIC from the
    results of an Altaipony fit

    Parameters:
        results     dict    Results from Altaipony fit

    Returns:
        chi2       float   Chi squared
        bic         float   Bayesian Information Criteria
    """

    # Generate the model lightcurve, following Altaipony's method, and convert to magnitudes
    flare_model = flare_model_davenport2014(
        results[0]['time'], results[0]['t_peak'], results[0]['fwhm'], results[0]['amplitude']
    )
    baseline = build_baseline(results[0]['time'], results[0]['params'][:5])
    flux_lc = baseline + flare_model
    model_mag, _, _, _ = utils.flux_to_mag(flux_lc, np.ones(len(flux_lc)))
    data_mag, data_mag_err, _, _ = utils.flux_to_mag(results[0]['flux'], results[0]['flux_err'])

    # Calculate diagnostics
    # Nparam = 3
    chi2 = np.sum((data_mag - model_mag)**2 / (float(len(data_mag)) - 3.0))
    bic = chi2 + 3.0 * np.log(len(data_mag))

    return chi2, bic