from custom_code.models import SourceDiagnostics
from .variable_stars import find_nearest_rges_variable_catalog, calc_periodogram
from .diagnostics import calc_baseline_magnitude
from custom_code import data_utils
import logging

logger = logging.getLogger(__name__)

def run_source_diagnostics(target):
    diagnostics = {
        'classification': 'Microlensing PSPL',
        'category': 'Microlensing stellar/planet',
        'source_magnitude': 0.0,
        'source_mag_error': 0.0,
        'baseline_magnitude': 0.0,
        'baseline_mag_error': 0.0,
        'nearest_flare_star': '',
        'angular_separation_flare_star': 0.0,
        'nearest_variable_star': '',
        'angular_separation_variable': 0.0,
        'nearest_variable_type': '',
        'max_peak_periodogram': 0.0,
        'period': 0.0
    }

    default_passband = 'Roman_F146'
    datasets = data_utils.get_full_lightcurve(target, bandpass=default_passband)
    lightcurve = datasets.get(default_passband)

    diagnostics = find_nearest_rges_variable_catalog(target, diagnostics)
    diagnostics = calc_periodogram(target, lightcurve, diagnostics)
    diagnostics = calc_baseline_magnitude(lightcurve, default_passband, diagnostics)

    entry = SourceDiagnostics.objects.create(target=target, **diagnostics)
    logger.info('Computed source diagnostics for ' + target.name)

    return entry
