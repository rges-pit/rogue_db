from custom_code.models import SourceDiagnostics
from .variable_stars import find_nearest_rges_variable_catalog, calc_periodogram

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
    diagnostics = find_nearest_rges_variable_catalog(target, diagnostics)
    diagnostics = calc_periodogram(target, diagnostics)

    SourceDiagnostics.objects.create(
        target=target,
        defaults=diagnostics
    )