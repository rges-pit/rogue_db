import io

from custom_code import data_utils
from custom_code.models import Event
from custom_code import data_utils
from custom_code import (pylima_fit_functions, general_fit_functions,
            diagnostics, flare_fit_functions)
from django.core.files.base import ContentFile
import numpy as np
import matplotlib.pyplot as plt
import logging

logger = logging.getLogger(__name__)

def generate_event_lightcurves(lcevent):
    """
    Function to create a thumbnail image of the lightcurve segment of an
    event.  Since this is primarily aimed at Roman data the lightcurve we
    look for here is F146.
    """

    datasets = data_utils.get_reduced_data(lcevent)

    # Lightcurve array columns: ts, brightness, brightness_error
    bandpass = 'F146'
    if bandpass in datasets.keys():
        lc = datasets[bandpass]

        # Select only the datapoints during the event
        event_end = lcevent.start_time + lcevent.duration
        idx = np.where((lc[:,0] >= lcevent.start_time) & (lc[:,0] <= event_end))[0]

        # Plot lightcurve
        dt = 2460000.0
        fig, ax = plt.subplots(1,1, figsize=(6,4))
        ax.errorbar(
            lc[idx,0]-dt, lc[idx,1], yerr=lc[idx,2],
            marker='.', c='purple'
        )
        ax.set_xlabel('JD-' + str(dt) + ' [days]')
        ax.set_ylabel('Mag [' + bandpass + ']')
        ax.set_yinverted(True)

        # Render to an in-memory buffer rather than a literal path, so the
        # write goes through Event.thumbnail's storage backend (local disk
        # now, S3 later) instead of hardcoding a filesystem location.
        buf = io.BytesIO()
        fig.savefig(buf, format='png')
        plt.close(fig)

        filename = lcevent.target.name + '_' + lcevent.event_id + '_lc.png'
        # save=False: FieldFile.save() with save=True calls instance.save()
        # with no update_fields, which wouldn't satisfy on_event_saved's
        # update_fields guard and would spuriously re-trigger the moving-object
        # check. .update() persists the field without going through post_save.
        lcevent.thumbnail.save(filename, ContentFile(buf.getvalue()), save=False)
        Event.objects.filter(pk=lcevent.pk).update(thumbnail=lcevent.thumbnail.name)

def run_event_modeling(lcevent):
    """
    Function to run the standard sequence of model fits to an event lightcurve segment

    Parameters:
        lcevent Event
    """

    logger.info('Starting modeling for ' + lcevent.target.name + ', event ' + lcevent.event_id)

    # Search for secondary peaks for the same source
    diagnostics.second_peak_diagnostics(lcevent)

    # Straight line model fit
    straightline_results = general_fit_functions.run_event_straightline_fit(lcevent)
    straightline_model = data_utils.store_straightline_model_parameters(
        lcevent, straightline_results, 'Straight line'
    )
    data_utils.store_model_lightcurve(lcevent, straightline_results, 'straight_line')

    # Baseline model fit
    baseline_results = general_fit_functions.run_baseline_fit(lcevent)
    baseline_model = data_utils.store_straightline_model_parameters(
        lcevent, baseline_results, 'Baseline'
    )
    data_utils.store_baseline_diagnostics(lcevent, baseline_results)

    # Calculate coverage and skew
    results = {}
    results['coverage_fraction'] = general_fit_functions.calc_coverage(lcevent)
    results['symmetry'] = general_fit_functions.calc_symmetry(lcevent)
    data_utils.store_event_statistics(lcevent, results)

    # Fit microlensing models and calculate diagnostics
    pylima_results = pylima_fit_functions.run_fit(lcevent, verbose=False)
    data_utils.store_pylima_model_lightcurves(lcevent, pylima_results)
    pspl_model, fspl_model = data_utils.store_microlensing_model_parameters(
        lcevent, pylima_results
    )
    diagnostics.calc_mulens_diagnostics(
        lcevent, pspl_model, fspl_model, straightline_model
    )
    best_mulens = diagnostics.get_best_mulens_model(pspl_model, fspl_model)
    data_utils.generate_corner_plot(
        pspl_model, pylima_results['pspl'],
        lcevent.target.name + '_' + str(lcevent.event_id) + '_PSPL_corner_plot.png'
    )
    data_utils.generate_corner_plot(
        fspl_model, pylima_results['fspl'],
        lcevent.target.name + '_' + str(lcevent.event_id) + '_FSPL_corner_plot.png'
    )

    # Fit flare models and calculate diagnostics
    davenport_results = flare_fit_functions.run_davenport_flare_fit(lcevent)
    davenport_flare = data_utils.store_davenportflare_model_parameters(lcevent, davenport_results)
    data_utils.store_model_lightcurve(
        lcevent, davenport_results, 'davenport_flare'
    )
    data_utils.generate_corner_plot(
        davenport_flare, davenport_results,
        lcevent.target.name + '_' + str(lcevent.event_id) + '_davenport_corner_plot.png'
    )
    pitkin_results = flare_fit_functions.run_pitkin_flare_model_fit(lcevent)
    pitkin_flare = data_utils.store_pitkinflare_model_parameters(
        lcevent, pitkin_results
    )
    data_utils.store_model_lightcurve(lcevent, pitkin_results, 'pitkin_flare')
    diagnostics.calc_flare_diagnostics(lcevent, best_mulens, davenport_flare, pitkin_flare)
    data_utils.generate_corner_plot(
        pitkin_flare, pitkin_results,
        lcevent.target.name + '_' + str(lcevent.event_id) + '_pitkin_corner_plot.png'
    )

    logger.info('Completed modeling for ' + lcevent.target.name + ', event ' + lcevent.event_id)