"""
Information descriptions of all parameters in the Event Detail page

The following descriptions appear when users click the small "i" icon beside the name of each parameter.

Conventions that hold throughout: times are Julian Dates, durations are in days, and magnitudes are as
astronomers use them: a smaller magnitude is a brighter source.
"""

EVENT_PARAMETERS = {
    'start_time': (
        'Start time [JD]',
        'Julian Date at which the event begins, as given by the alert that detected it.',
    ),
    'duration': (
        'Duration [d]',
        'Length of the event window in days, from the start_time of the alert. The diagnostics on this '
        'page are measured within this window.',
    ),
    'peak_mag': (
        'Peak mag',
        'Magnitude of the source at the peak of the event: its brightest point in the Roman F146 '
        'lightcurve within the event window. ',
    ),
    'coverage_fraction': (
        'Coverage',
        'Fraction of the event window that has data: the number of F146 points in the window times the '
        'median interval between points, divided by the duration. A value of 1 means the '
        'event is fully sampled; low values mean there are gaps in the data.',
    ),
    'symmetry': (
        'Symmetry',
        'Skewness of the F146 magnitudes measured within the event window. 0 means the magnitudes are '
        'distributed symmetrically; positive values mean a longer tail towards fainter magnitudes, '
        'negative values a longer tail towards brighter ones.',
    ),
    'time_to_second_peak': (
        'Δt 2nd peak [d]',
        'Time in days from this event to the nearest other event of the same source, measured between '
        'the midpoints of the two event windows. Negative if the other event is earlier. Blank if the '
        'source has no other event.',
    ),
    'second_peak_mag': (
        '2nd peak mag',
        "Peak magnitude of the nearest other event of the same source. Blank if the source has "
        "no other event, or that event hasn't been modeled.",
    ),
    'Npoint_above_3sigma': (
        'N > 3σ',
        'The longest run of consecutive F146 points during the event that are brighter than the baseline '
        'by more than 3σ, where σ is the scatter of the baseline. A long run points to a real, sustained '
        'brightening rather than noise.',
    ),
    'nearest_moving_object': (
        'Nearest moving obj.',
        "Name of the closest known asteroid or comet identified by JPL's Small-Body Identification Tool "
        'within 2 arcseconds of the source at the time of the event as seen from Roman. Blank '
        'if none was found, or if the JPL service could not be reached.',
    ),
    'angular_separation_moving_object': (
        'Sep. moving obj. [arcsec]',
        'Angular separation between the source and that moving object. Blank if no object was found.',
    ),
    'Nlinked_events': (
        'N linked events',
        'Number of other events in the same cluster as this one, in a cluster analysis of all events by '
        'position and time. 0 means the event is isolated; a large number means many events '
        'occurred close together on the sky and in time, which can point to a common cause, such as an '
        'artefact in the images, rather than independent astrophysical events.',
    ),
    'DIA_centroid_shift': (
        'DIA centroid shift',
        "Shift of the source's centroid measured in the difference images, a test of whether the "
        'variability comes from the source itself or from a neighbouring star. Not calculated yet, so '
        'currently blank.',
    ),
    'PSF_centroid_shift': (
        'PSF centroid shift',
        "Shift of the source's centroid measured by PSF fitting, a test of whether the variability comes "
        'from the source itself or from a neighbouring star. Not calculated yet, so currently blank.',
    ),
    'frac_below_baseline': (
        'Frac below baseline',
        "Fraction of all the source's F146 points, not only those in the event, that are fainter than the "
        'baseline by more than 1σ. The baseline is the median level of a straight-line fit to the points '
        'near the median magnitude, and σ is the scatter of that fit.',
    ),
    'max_excursion_below_baseline': (
        'Max below base [mag]',
        'The greatest departure towards fainter magnitudes of any of the points used for the baseline '
        'fit from the baseline level. ',
    ),
    'bestmulens_model_type': (
        'Best μlens',
        'Which microlensing model fits the event better: PSPL (point source, point lens) or FSPL (finite '
        'source, point lens), judged by the lower reduced χ².',
    ),
    'delta_chi2_PSPL': (
        'Δχ² PSPL',
        'Difference in χ² between the PSPL microlensing model and a straight-line fit to the event: '
        'χ²(PSPL) − χ²(line). Negative means the microlensing model fits better; a large negative value '
        'is strong evidence that the event is more than noise on a constant source.',
    ),
    'delta_BIC_PSPL': (
        'ΔBIC PSPL',
        'Difference in the Bayesian Information Criterion between the PSPL model and the straight line: '
        'BIC(PSPL) − BIC(line). BIC is χ² plus a penalty for each fitted parameter (k ln n, for k '
        'parameters and n points), so a negative value means PSPL is preferred even after that penalty. '
        'A difference beyond about 10 is conventionally taken as strong evidence.',
    ),
    'delta_chi2_FSPL': (
        'Δχ² FSPL',
        'Difference in χ² between the FSPL microlensing model and a straight-line fit to the event: '
        'χ²(FSPL) − χ²(line). Negative means the finite-source model fits better.',
    ),
    'delta_BIC_FSPL': (
        'ΔBIC FSPL',
        'Difference in the Bayesian Information Criterion between the FSPL model and the straight line: '
        'BIC(FSPL) − BIC(line). Negative means FSPL is preferred even after the penalty for its extra '
        'parameter.',
    ),
    'bestflare_model_type': (
        'Best flare',
        'Which flare model fits the event better: Davenport (Davenport et al. 2014) or Pitkin (Pitkin et '
        'al. 2014), judged by the lower reduced χ².',
    ),
    'delta_chi2_PSPL_bestflare': (
        'Δχ² PSPL best flare',
        'Difference in χ² between the PSPL model and the better of the two flare models: '
        'χ²(PSPL) − χ²(flare). Negative means microlensing fits better than a stellar flare; positive '
        'means the flare fits better.',
    ),
    'delta_BIC_PSPL_bestflare': (
        'ΔBIC PSPL best flare',
        'Difference in BIC between the PSPL model and the better of the two flare models: '
        'BIC(PSPL) − BIC(flare). Negative means microlensing is preferred, positive that the flare is.',
    ),
    'delta_chi2_FSPL_bestflare': (
        'Δχ² FSPL best flare',
        'Difference in χ² between the FSPL model and the better of the two flare models: '
        'χ²(FSPL) − χ²(flare). Negative means microlensing fits better than a stellar flare; positive '
        'means the flare fits better.',
    ),
    'delta_BIC_FSPL_bestflare': (
        'ΔBIC FSPL best flare',
        'Difference in BIC between the FSPL model and the better of the two flare models: '
        'BIC(FSPL) − BIC(flare). Negative means microlensing is preferred, positive that the flare is.',
    ),
}

UNCERTAINTY = ' The value after ± is its 1σ uncertainty.'

MODEL_PARAMETERS = {
    't0': (
        't0',
        'Time of closest approach of the source to the lens, which is the time of the peak of the '
        'microlensing event, in Julian Date.' + UNCERTAINTY,
    ),
    'u0': (
        'u0',
        'Impact parameter: the smallest angular separation between the source and the lens, in units of '
        'the Einstein radius. The smaller it is, the higher the peak magnification.' + UNCERTAINTY,
    ),
    'tE': (
        'tE',
        'Einstein timescale in days: the time the source takes to cross the Einstein radius of the lens. '
        'It sets how long the event lasts.' + UNCERTAINTY,
    ),
    'rho': (
        'rho',
        'Angular radius of the source star in units of the lens’s Einstein radius (finite-source models '
        'only). ' + UNCERTAINTY,
    ),
    'A': (
        'A',
        'Magnification at the peak of the event: the factor by which the lens brightens the source.'
        + UNCERTAINTY,
    ),
    'blend_parameters': (
        'blend parameters',
        'Magnitudes of the lensed source and of the blend, the light from other stars that falls in the '
        'same pixels and is not magnified, with their uncertainties.',
    ),
    't_peak': (
        't peak',
        'Time of the peak of the flare, in Julian Date.' + UNCERTAINTY,
    ),
    'peak_amplitude': (
        'peak amplitude',
        'Height of the flare at its peak, relative to the baseline level of the lightcurve.' + UNCERTAINTY,
    ),
    't_FWHM': (
        't FWHM',
        'Full width at half maximum of the flare in days: how long it stays above half of its peak '
        'amplitude (Davenport model).' + UNCERTAINTY,
    ),
    'tau_gaussian_rise': (
        'tau gaussian rise',
        'Timescale in days of the flare’s rise to its peak, which follows a Gaussian (Pitkin model).'
        + UNCERTAINTY,
    ),
    'tau_exponential_decay': (
        'tau exponential decay',
        'Timescale in days of the flare’s decline after its peak, which follows an exponential (Pitkin '
        'model).' + UNCERTAINTY,
    ),
    'gradient': (
        'gradient',
        'Slope of the straight line in magnitudes per day.' + UNCERTAINTY,
    ),
    'intercept': (
        'intercept',
        'Magnitude of the straight line at JD 0.' + UNCERTAINTY,
    ),
    'chisq': (
        'chisq',
        'χ² of the fit: the sum of the squared residuals, each divided by its photometric uncertainty. '
        'Lower is better.',
    ),
    'red_chisq': (
        'red chisq',
        'Reduced χ²: χ² divided by the degrees of freedom (the number of data points minus the number of '
        'fitted parameters). A value near 1 means the model fits within the uncertainties.',
    ),
    'BIC': (
        'BIC',
        'Bayesian Information Criterion: χ² plus a penalty of ln n for each of the k fitted parameters '
        '(n is the number of points). Lower is better, and it allows models with different numbers of '
        'parameters to be compared fairly.',
    ),
    'fit_method': (
        'fit method',
        'How the model was fitted: MCMC samples the whole distribution of parameter values that fit the '
        'data, while the other methods are least-squares fits that find a single best fit.',
    ),
    'tau': (
        'tau',
        'Integrated autocorrelation time of the MCMC chains, in steps: roughly how many steps it takes '
        'to get an independent sample. Shorter is better.',
    ),
    'tau_threshold': (
        'tau threshold',
        'The largest τ at which the fit counts as converged: one fiftieth of the length of the chains, '
        'as the chains should be at least 50 τ long. If τ is larger than this, the chains are too short '
        'and the result is less reliable.',
    ),
}

DESCRIPTIONS = {'event': EVENT_PARAMETERS, 'model': MODEL_PARAMETERS}


def describe(scope, name):
    """(title, description) of a parameter, or None if it hasn't any. scope is 'event' or 'model'."""
    return DESCRIPTIONS[scope].get(name)
