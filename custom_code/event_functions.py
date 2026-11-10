import io
from custom_code.models import Event, ModelingProcess, EventDiagnostics
from custom_code import data_utils
from custom_code import (pylima_fit_functions, general_fit_functions,
            diagnostics, flare_fit_functions, utils, solar_system)
from custom_code import __version__
from django.core.files.base import ContentFile
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, UTC
import logging

logger = logging.getLogger(__name__)

def event_file_stem(lcevent):
    """
    The start of the names of an event's files: its source's name and its event ID. The IDs of
    events made from alerts already begin with the source's name (see get_event_id), and the
    name isn't repeated.
    """
    name, event_id = lcevent.target.name, str(lcevent.event_id)
    if event_id.startswith(name + '_'):
        return event_id
    return name + '_' + event_id


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

        buf = io.BytesIO()
        fig.savefig(buf, format='png')
        plt.close(fig)

        filename = event_file_stem(lcevent) + '_lc.png'
        utils.replace_image_file(lcevent.thumbnail, filename, ContentFile(buf.getvalue()))
        Event.objects.filter(pk=lcevent.pk).update(thumbnail=lcevent.thumbnail.name)

def run_event_modeling(lcevent, nlinked_events=None):
    """
    Function to run the standard sequence of model fits to an event lightcurve segment, and to record
    on the event how far it got: Running while it's at it, then Complete (with the time) or, if any
    step raises an error, Failed. An event that is neither is left out of what's reported as modeled,
    so a failure mustn't leave it as Running, which would look the same as one still being worked on.
    The error isn't hidden: it's raised again for the caller to report.

    Parameters:
        lcevent Event
    """

    logger.info('Starting modeling for ' + lcevent.target.name + ', event ' + lcevent.event_id)
    ts = datetime.now(UTC)
    process = ModelingProcess.objects.create(
        event=lcevent,
        started_at=ts,
        status=ModelingProcess.ProcessStatus.running,
        code_version=__version__.get_version()
    )

    try:
        _fit_event_models(lcevent, process, nlinked_events)
    except Exception:
        ModelingProcess.objects.filter(pk=process.pk).update(
            status=ModelingProcess.ProcessStatus.failed, completed_at=datetime.now(UTC)
        )
        logger.error('Modeling failed for ' + lcevent.target.name + ', event ' + lcevent.event_id)
        raise

    ModelingProcess.objects.filter(pk=process.pk).update(
        status=ModelingProcess.ProcessStatus.complete, completed_at=datetime.now(UTC)
    )

    logger.info('Completed modeling for ' + lcevent.target.name + ', event ' + lcevent.event_id)

def _fit_event_models(lcevent, process, nlinked_events=None):
    """The steps of run_event_modeling: the diagnostics and each model fit, stored as they're made"""

    results = {'process': process}
    if nlinked_events is not None:
        results['Nlinked_events'] = nlinked_events

    # Generate the thumbnail of the event
    generate_event_lightcurves(lcevent)

    # Search for known Solar System objects close to this event
    closest_name, ang_sep = solar_system.find_moving_objects_near_event(lcevent)
    results['nearest_moving_object'] = closest_name
    results['angular_separation_moving_object'] = ang_sep

    # Estimate peak mag
    results['peak_mag'] = data_utils.estimate_peak_mag(lcevent)

    # Search for secondary peaks for the same source
    results = diagnostics.second_peak_diagnostics(lcevent, results)

    # Straight line model fit
    straightline_results = general_fit_functions.run_event_straightline_fit(lcevent)
    straightline_model = data_utils.store_straightline_model_parameters(
        lcevent, process, straightline_results, 'Straight line'
    )
    data_utils.store_model_lightcurve(lcevent, straightline_results, 'straight_line')

    # Baseline model fit
    baseline_results = general_fit_functions.run_baseline_fit(lcevent)
    baseline_model = data_utils.store_straightline_model_parameters(
        lcevent, process, baseline_results, 'Baseline'
    )
    results['frac_below_baseline'] = baseline_results['frac_below_baseline']
    results['max_excursion_below_baseline'] = baseline_results['max_excursion_below_baseline']
    results['Npoint_above_3sigma'] = baseline_results['Npoint_above_3sigma']

    # Calculate coverage and skew
    results['coverage_fraction'] = general_fit_functions.calc_coverage(lcevent)
    results['symmetry'] = general_fit_functions.calc_symmetry(lcevent)

    # Fit microlensing models and calculate diagnostics
    pylima_results = pylima_fit_functions.run_fit(lcevent, verbose=False)
    data_utils.store_pylima_model_lightcurves(lcevent, pylima_results)
    pspl_model, fspl_model = data_utils.store_microlensing_model_parameters(
        lcevent, process, pylima_results
    )
    results = diagnostics.calc_mulens_diagnostics(
        pspl_model, fspl_model, straightline_model, results
    )
    data_utils.generate_corner_plot(
        pspl_model, pylima_results['pspl'],
        event_file_stem(lcevent) + '_PSPL_corner_plot_' + str(process.pk) + '.png'
    )
    data_utils.generate_corner_plot(
        fspl_model, pylima_results['fspl'],
        event_file_stem(lcevent) + '_FSPL_corner_plot_' + str(process.pk) + '.png'
    )

    # Fit flare models and calculate diagnostics
    davenport_results = flare_fit_functions.run_davenport_flare_fit(lcevent)
    davenport_flare = data_utils.store_davenportflare_model_parameters(
        lcevent, process, davenport_results
    )
    data_utils.store_model_lightcurve(
        lcevent, davenport_results, 'davenport_flare'
    )
    data_utils.generate_corner_plot(
        davenport_flare, davenport_results,
        event_file_stem(lcevent) + '_davenport_corner_plot_' + str(process.pk) + '.png'
    )
    pitkin_results = flare_fit_functions.run_pitkin_flare_model_fit(lcevent)
    pitkin_flare = data_utils.store_pitkinflare_model_parameters(
        lcevent, process, pitkin_results
    )
    data_utils.store_model_lightcurve(lcevent, pitkin_results, 'pitkin_flare')
    results = diagnostics.compare_flare_models(
        pspl_model, fspl_model, davenport_flare, pitkin_flare, results
    )
    data_utils.generate_corner_plot(
        pitkin_flare, pitkin_results,
        event_file_stem(lcevent) + '_pitkin_corner_plot_' + str(process.pk) + '.png'
    )

    EventDiagnostics.objects.create(**results)