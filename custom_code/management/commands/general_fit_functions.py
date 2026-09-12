from custom_code.management.commands import data_utils
import logging
import numpy as np

logger = logging.getLogger(__name__)

def run_straightline_fit(lcevent):
    """
    Function to fit a straight line to an Event lightcurve segment

    Parameters:
        lcevent   (Lightcurve) Event object

    Returns:
        coeffs      array       Straight line fit coefficients (intercept, gradient)
        chi2        float       Chi-squared value of the fit
        BIC         float       Bayesian Information Criteria of the fit
    """

    logger.info('Starting starting straight line fit to event for source ' + lcevent.target.name)

    # Retrieve Roman's primary timeseries photometry from the DB
    datasets = data_utils.get_reduced_data(lcevent)
    lightcurve = data_utils.fetch_lightcurve(datasets, dataset_id='W146')

    # Fit a straight line (f(x) = p[0] + p[1]*x) to the lightcurve segment
    # and generate fitted lightcurve
    coeffs, residuals, rank, singular_values, rcond, covar = np.polyfit(
        lightcurve[:,0], lightcurve[:,1], deg=1, w=1.0/lightcurve[:,2],
        full=False, cov=True
    )
    model_mag = coeffs[0] + coeffs[1] * lightcurve[:,0]

    # Calculate the chi2 and BIC = chi2 + k ln(n) of this model to the lightcurve
    chi2 = np.sum(((lightcurve[:,1] - model_mag) / lightcurve[:,2]) ** 2)
    bic = chi2 + len(coeffs) * np.log(len(lightcurve))

    # Calculate diagnostics for the straight line fit
    mean_mag = np.median(model_mag)
    frac_below_baseline = float(len(np.where(lightcurve[:,1] < mean_mag)[0])) / float(len(lightcurve))
    max_excursion_below_baseline = (lightcurve[:,1] - mean_mag).min()

    logger.info('Completed straight line fit with coefficients: ' + repr(coeffs))

    return {
        'coeffs': coeffs, 'chisq': chi2, 'BIC': bic,
        'covar': covar, 'frac_below_baseline': frac_below_baseline,
        'max_excursion_below_baseline': max_excursion_below_baseline
    }