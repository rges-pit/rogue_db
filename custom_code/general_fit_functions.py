from custom_code import data_utils, diagnostics
import logging
import numpy as np
import scipy.stats as stats
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

def run_event_straightline_fit(lcevent):
    """
    Function to fit a straight line to an Event lightcurve segment

    Parameters:
        lcevent   (Lightcurve) Event object

    Returns:
        coeffs      array       Straight line fit coefficients (intercept, gradient)
        chi2        float       Chi-squared value of the fit
        BIC         float       Bayesian Information Criteria of the fit
    """

    logger.info('Starting straight line fit to event for source ' + lcevent.target.name)

    # Retrieve Roman's primary timeseries photometry from the DB
    datasets = data_utils.get_reduced_data(lcevent)
    lightcurve = data_utils.fetch_lightcurve(datasets)

    # Set a cap of a minimum of ten points for a sensible fit
    if len(lightcurve) > 10:
        # Fit a straight line (f(x) = p[0]*x + p[1]) to the lightcurve segment
        # and generate fitted lightcurve
        try:
            coeffs, covar = np.polyfit(
                lightcurve[:,0], lightcurve[:,1], deg=1, w=1.0/lightcurve[:,2],
                full=False, cov=True
            )
        except numpy.linalg.LinAlgError:
            coeffs = np.array([0.0, 0.0])
            covar = np.array([])

        model_lc = np.zeros((len(lightcurve[:,0]), 2))
        model_lc[:,0] = lightcurve[:,0]
        model_lc[:,1] = coeffs[0] * lightcurve[:,0] + coeffs[1]

        # Calculate the chi2 and BIC = chi2 + k ln(n) of this model to the lightcurve
        chi2 = np.sum(((lightcurve[:,1] - model_lc[:,1]) / lightcurve[:,2]) ** 2)
        red_chi2 = chi2 / (float(len(lightcurve[:,0])) - 2.0)
        bic = chi2 + len(coeffs) * np.log(len(lightcurve))

        logger.info('Completed straight line fit with coefficients: ' + repr(coeffs))

        return {
            'coeffs': coeffs, 'chisq': chi2, 'BIC': bic, 'red_chisq': red_chi2,
            'covar': covar,
            'model_lc': model_lc,
            'fit_method': 'polyfit'
        }

    else:
        logger.info('Insufficient valid data during event')
        return {
            'coeffs': np.zeros(0), 'chisq': None, 'BIC': None, 'red_chisq': None,
            'covar': np.zeros(0),
            'fit_method': 'polyfit'
        }

def run_baseline_fit(lcevent):
    """
    Function to fit a straight line model to the baseline target's lightcurve,
    i.e. the whole lightcurve with the intervals flagged as events removed.

    Parameters:
        lcevent  Event object
    """

    logger.info('Starting baseline fit to event for event ' + lcevent.event_id)

    # Retrieve Roman's primary timeseries photometry from the DB, excluding events
    datasets = data_utils.get_baseline_data(lcevent, source_name='Roman_F146')
    lightcurve = data_utils.fetch_lightcurve(datasets)
    full_datasets = data_utils.get_reduced_data(lcevent, source_name='Roman_F146')
    full_lightcurve = data_utils.fetch_lightcurve(full_datasets)

    # Set a cap of a minimum of ten points for a sensible fit
    if len(lightcurve) > 10:

        fig, ax = plt.subplots(1, 1, figsize=(6, 4))
        dt = float(int(lightcurve[0,0]))
        ax.errorbar(
            lightcurve[:, 0] - dt, lightcurve[:, 1], yerr=lightcurve[:, 2],
            marker='.', c='purple'
        )
        ax.set_xlabel('JD-' + str(dt) + ' [days]')
        ax.set_ylabel('Mag')
        ax.set_yinverted(True)
        plt.savefig('./test_plot.png')

        # Fit a straight line (f(x) = p[0]*x + p[1]) to the lightcurve segment
        # and generate fitted lightcurve
        coeffs, covar = np.polyfit(
            lightcurve[:,0], lightcurve[:,1], deg=1, w=1.0/lightcurve[:,2],
            full=False, cov=True
        )

        model_lc = np.zeros((len(lightcurve[:,0]), 2))
        model_lc[:,0] = lightcurve[:,0]
        model_lc[:,1] = coeffs[0] * lightcurve[:,0] + coeffs[1]

        # Calculate the chi2 and BIC = chi2 + k ln(n) of this model to the lightcurve
        chi2 = np.sum(((lightcurve[:,1] - model_lc[:,1]) / lightcurve[:,2]) ** 2)
        red_chi2 = chi2 / (float(len(lightcurve[:, 0])) - 2.0)
        bic = chi2 + len(coeffs) * np.log(len(lightcurve))

        # Calculate diagnostics for the baseline fit
        mean_mag = np.median(model_lc[:,1])
        frac_below_baseline = float(len(np.where(lightcurve[:,1] < mean_mag)[0])) / float(len(lightcurve))
        max_excursion_below_baseline = (lightcurve[:,1] - mean_mag).min()
        npoints = diagnostics.calc_npoints_above_baseline(
            lcevent,
            lightcurve,
            full_lightcurve
        )

        logger.info('Completed baseline line fit with coefficients: ' + repr(coeffs))

        return {
            'coeffs': coeffs, 'chisq': chi2, 'BIC': bic, 'red_chisq': red_chi2,
            'model_lc': model_lc,
            'covar': covar, 'frac_below_baseline': frac_below_baseline,
            'max_excursion_below_baseline': max_excursion_below_baseline,
            'Npoint_above_3sigma': npoints,
            'fit_method': 'polyfit'
        }

    else:
        logger.info('No valid data found')
        return {
            'coeffs': np.zeros(0), 'chisq': None, 'BIC': None, 'red_chisq': None,
            'covar': np.zeros(0), 'frac_below_baseline': None,
            'max_excursion_below_baseline': None,
            'Npoint_above_3sigma': None,
            'fit_method': 'polyfit'
        }

def calc_coverage(lcevent):
    """
    Function to estimate the fraction of the event that is covered with datapoints.
    The number of datapoints during the event is easy to calculate but this doesn't directly
    compare with the duration of the event without knowing the interval between points.
    So this is estimated from the median interval

    Parameters:
        lcevent  Event object

    Returns:
        frac_cover float
    """

    datasets = data_utils.get_reduced_data(lcevent, source_name='Roman_F146')
    lightcurve = data_utils.fetch_lightcurve(datasets)

    if len(lightcurve) > 0:
        # Estimate the median interval between datapoints
        dt = float(np.median(lightcurve[1:,0] - lightcurve[:-1,0]))

        # Calculate the number of datapoints obtained during the event
        idx1 = np.where(lightcurve[:,0] >= lcevent.start_time)[0]
        idx2 = np.where(lightcurve[:,0] <= lcevent.start_time + lcevent.duration)[0]
        idx = list(set(idx1).intersection(set(idx2)))

        return min(len(idx) * dt / lcevent.duration, 1.0)

    else:
        return 0.0

def calc_symmetry(lcevent):
    """
    Function to estimate the skewness of the event lightcurve
    Skew = 0 indicates perfect symmetry
    Positive value indicates a long tail to the right of the peak
    Negative value indicates a long tail to the left of the peak
    """

    datasets = data_utils.get_reduced_data(lcevent, source_name='Roman_F146')
    lightcurve = data_utils.fetch_lightcurve(datasets)

    if len(lightcurve) > 0:
        # Get section of lightcurve within the event duration:
        idx1 = np.where(lightcurve[:, 0] >= lcevent.start_time)[0]
        idx2 = np.where(lightcurve[:, 0] <= lcevent.start_time + lcevent.duration)[0]
        idx = list(set(idx1).intersection(set(idx2)))

        skew = float(stats.skew(lightcurve[idx,1]))

        return skew
    else:
        return np.nan

