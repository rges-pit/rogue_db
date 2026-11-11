import numpy as np
from scipy.cluster.hierarchy import single, fcluster
from scipy.spatial.distance import pdist
from custom_code.models import Event, EventDiagnostics, ModelingProcess
import matplotlib.pyplot as plt
import logging

logger = logging.getLogger(__name__)

def calc_mulens_diagnostics(pspl_model, fspl_model, straightline_model, results):
    """
    Function to compare the results of PyLIMA model fits for PSPL and FSPL
    for a single event
    """
    best_mulens = get_best_event_model(pspl_model, fspl_model)
    if best_mulens:
        results['bestmulens_model_type'] = str(best_mulens.model_type).replace('microlensing','').strip()

    if pspl_model and straightline_model:
        results = compare_mulens_with_straightline(pspl_model, straightline_model, results)

    if fspl_model and straightline_model:
        results = compare_mulens_with_straightline(fspl_model, straightline_model, results)

    return results

def get_best_event_model(model1, model2):
    """
    Function returns the microlensing model with the lowest reduced chisq.
    """

    if model1 and model2:
        if getattr(model1, 'red_chisq') <= getattr(model2, 'red_chisq'):
            best_model = model1
        else:
            best_model = model2
    elif model1 and not model2:
        best_model = model1
    elif model2 and not model1:
        best_model = model2
    else:
        best_model = None

    return best_model

def compare_mulens_with_straightline(model1, model2, results):
    """
    Function to compare the goodness-of-fit parameters for the two models given.
    The models are order so that the straight line model is always second
    """

    # Calculate the difference between the chi2 values and the BIC
    delta_chisq = model1.chisq - model2.chisq
    delta_bic = model1.BIC - model2.BIC

    # Add these to the results, which become the EventDiagnostics of the modeling
    if model1.model_type == 'PSPL microlensing' and model2.model_type == 'Straight line':
        results['delta_chi2_PSPL'] = delta_chisq
        results['delta_BIC_PSPL'] = delta_bic

    elif model1.model_type == 'FSPL microlensing' and model2.model_type == 'Straight line':
        results['delta_chi2_FSPL'] = delta_chisq
        results['delta_BIC_FSPL'] = delta_bic

    return results

def compare_flare_models(pspl_model, fspl_model, davenport_model, pitkin_model, results):
    """
    Function to compare the results of fitting different flare models to this event,
    and to calculate the diagnostics comparing the flare models with microlensing models

    Parameters:
        event               Event object
        mulens_model        EventModel for microlensing
        davenport_model   EventModel results of Davenport model fit
        pitkin_model      EventModel        results of Pitkin model fit
        results     Dict        Parameters to be stored as EventDiagnostics
    """

    best_flare = get_best_event_model(davenport_model, pitkin_model)
    if not best_flare:
        return results
    results['bestflare_model_type'] = str(best_flare.model_type).replace('flare','').strip()

    if pspl_model:
        results['delta_chi2_PSPL_bestflare'] = pspl_model.chisq - best_flare.chisq
        results['delta_BIC_PSPL_bestflare'] = pspl_model.BIC - best_flare.BIC
    if fspl_model:
        results['delta_chi2_FSPL_bestflare'] = fspl_model.chisq - best_flare.chisq
        results['delta_BIC_FSPL_bestflare'] = fspl_model.BIC - best_flare.BIC

    return results

def calc_npoints_above_baseline(lcevent, baseline_lightcurve, event_lightcurve):
    """
    Function to calculate the number of consecutive points points more than
    3 sigma above baseline
    """

    # Identify those datapoints that are more than 3sigma above the median baseline
    median_mag = np.median(baseline_lightcurve[:,1])
    stddev = (baseline_lightcurve[:,1] - median_mag).std()

    idx1 = np.where(event_lightcurve[:,1] < median_mag - 3.0*stddev)[0]

    # Identify those datapoints within the event
    idx2 = np.where(event_lightcurve[:,0] >= lcevent.start_time)[0]
    idx3 = np.where(event_lightcurve[:,0] <= lcevent.start_time + lcevent.duration)[0]
    idx4 = set(idx2).intersection(set(idx3))
    idx = list(sorted(idx4.intersection(set(idx1))))

    # Identify groups of consecutive datapoints, and find the length of the
    # group with the most entries
    npoints = 0
    if len(idx) > 0:
        groups = np.split(idx, np.where(np.diff(idx) != 1)[0] + 1)
        npoints = np.array([len(entry) for entry in groups]).max()

    return npoints

def second_peak_diagnostics(e, results):
    """Check to see if there is more than one event associated with this target"""

    event_list = Event.objects.filter(target=e.target).order_by('-start_time')
    if len(event_list) > 1:

        # Identify the nearest event to this one in the list
        mid_event = e.start_time + e.duration/2.0
        delta_mid_event_times = np.array(
            [(et.start_time + et.duration/2.0)-mid_event for et in event_list if e != et]
        )
        et_idx = np.argmin(abs(delta_mid_event_times))

        # Time to nearest other peak
        other_events = [et for et in event_list if e != et]
        results['time_to_second_peak'] = delta_mid_event_times[et_idx]

        # The other event's peak magnitude is from its latest completed modeling
        other_event_diag = EventDiagnostics.objects.filter(
            process__event=other_events[et_idx],
            process__status=ModelingProcess.ProcessStatus.complete,
            process__completed_at__isnull=False,
        ).order_by('-process__completed_at', '-process_id').first()
        if other_event_diag is not None:
            results['second_peak_mag'] = other_event_diag.peak_mag

    logger.info('Calculated second peak diagnostics')
    return results

def link_events(events_qs, plot=False):
    """
    Function to perform a cluster analysis on all Events in [RA, Dec, time] space,
    following the approach by Will DeRocco.

    Returns the number of other events in the cluster each event belongs to, as a dictionary of
    these numbers by the primary key of the Event. This is for the modeling of each event to record
    as one of its diagnostics: it depends on all the events, so can't be worked out from one alone.
    """

    # Prefilter events list to avoid any invalid entries
    events_list = [e for e in events_qs if e.target != None]
    logger.info('Performing cluster analysis on ' + str(len(events_list)) + ' events')

    peaks = np.array([
        [e.target.ra, e.target.dec, e.start_time+e.duration/2.0] for e in events_list
    ])

    condenseddistances = pdist(peaks)
    dendrogram = single(condenseddistances)

    # Assign a cluster to each Event in the list
    cluster = fcluster(dendrogram, 4, criterion="distance")  # 4" distance scale

    # Compile the members of each cluster
    clusters = [peaks[cluster == i + 1] for i in range(max(cluster))]

    if plot:
        plt.scatter(peaks.T[0], peaks.T[2], c=cluster)
        plt.savefig('./data/cluster_diagram.png')

    # For each Event, indicate the number of other members of the same cluster,
    # subtracting the Event itself from it's cluster membership
    linked = {}
    for i,e in enumerate(events_list):
        event_cluster = cluster[i] - 1  # Offset for Python array indexing
        linked[e.pk] = len(clusters[event_cluster]) - 1  # Exclude the current event from the total
    return linked

def calc_baseline_magnitude(lightcurve, passband, diagnostics):
    """
    Function to estimate the baseline magnitude of the source, using a median on the assumption
    that the majority of the points are at baseline
    """

    if lightcurve is None or len(lightcurve) == 0:
        logger.info('Skipping baseline magnitude: no ' + passband + ' datapoints available')
        return diagnostics

    median_mag = np.median(lightcurve[:,1])
    diagnostics['baseline_magnitude'] = median_mag
    diagnostics['baseline_mag_error'] = (lightcurve[:,1] - median_mag).std()
    diagnostics['baseline_mag_passband'] = passband

    return diagnostics