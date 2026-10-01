import numpy as np
from scipy.cluster.hierarchy import single, fcluster
from scipy.spatial.distance import pdist
from custom_code.models import Event
import matplotlib.pyplot as plt
import logging

logger = logging.getLogger(__name__)

def calc_mulens_diagnostics(event, pspl_model, fspl_model, straightline_model):
    """
    Function to compare the results of PyLIMA model fits for PSPL and FSPL
    for a single event
    """
    if pspl_model and straightline_model:
        compare_model_goodness_of_fit(event, pspl_model, straightline_model)

    if fspl_model and straightline_model:
        compare_model_goodness_of_fit(event, fspl_model, straightline_model)

def get_best_mulens_model(pspl_model, fspl_model):
    """
    Function returns the microlensing model with the lowest reduced chisq.
    """

    if pspl_model and fspl_model:
        if pspl_model.red_chisq <= fspl_model.red_chisq:
            best_model = pspl_model
        else:
            best_model = fspl_model
    else:
        best_model = None

    return best_model

def calc_flare_diagnostics(event, best_mulens, davenport_model, pitkin_model):
    """
    Function to compare the flare model fits with the best fitting microlensing model
    """

    if best_mulens and davenport_model:
        compare_model_goodness_of_fit(event, best_mulens, davenport_model)

    if best_mulens and pitkin_model:
        compare_model_goodness_of_fit(event, best_mulens, pitkin_model)

def compare_model_goodness_of_fit(event, model1, model2):
    """
    Function to compare the goodness-of-fit parameters for the two models given.
    The models are order so that the straight line model is always second
    """

    # Calculate the difference between the chi2 values and the BIC
    delta_chisq = model1.chisq - model2.chisq
    delta_bic = model1.BIC - model2.BIC

    # Store these parameters on the Event
    if model1.model_type == 'PSPL microlensing' and model2.model_type == 'Straight line':
        event.delta_chi2_PSPL = delta_chisq
        event.delta_BIC_PSPL = delta_bic
        event.save()
    elif model1.model_type == 'FSPL microlensing' and model2.model_type == 'Straight line':
        event.delta_chi2_FSPL = delta_chisq
        event.delta_BIC_FSPL = delta_bic
        event.save()
    elif model1.model_type == 'PSPL microlensing' and model2.model_type == 'Davenport flare':
        event.delta_chi2_PSPL_bestflare = delta_chisq
        event.delta_BIC_PSPL_bestflare = delta_bic
        event.save()
    elif model1.model_type == 'FSPL microlensing' and model2.model_type == 'Davenport flare':
        event.delta_chi2_FSPL_bestflare = delta_chisq
        event.delta_BIC_FSPL_bestflare = delta_bic
        event.save()

def compare_flare_models(event, mulens_model, davenport_model, pitkin_model):
    """
    Function to compare the results of fitting different flare models to this event,
    and to calculate the diagnostics comparing the flare models with microlensing models

    Parameters:
        event               Event object
        mulens_model        EventModel for microlensing
        davenport_model   EventModel results of Davenport model fit
        pitkin_model      EventModel        results of Pitkin model fit
    """

    if davenport_model.chisq <= pitkin_model.chisq:
        best_flare = davenport_model
    else:
        best_flare = pitkin_model

    delta_chisq = mulens_model.chisq - best_flare.chisq
    delta_bic = mulens_model.BIC - best_flare.BIC

    if mulens_model.model_type == 'PSPL microlensing':
        event.delta_chi2_PSPL_bestflare = delta_chisq
        event.delta_BIC_PSPL_bestflare = delta_bic
        event.save()
    elif mulens_model.model_type == 'FSPL microlensing':
        event.delta_chi2_FSPL_bestflare = delta_chisq
        event.delta_BIC_FSPL_bestflare = delta_bic
        event.save()

def calc_npoints_above_baseline(lcevent, baseline_lightcurve, event_lightcurve):
    """
    Function to calculate the number of consecutive points points more than
    3 sigma above baseline
    """

    # Identify those datapoints that are more than 3sigma above the median baseline
    median_mag = np.median(baseline_lightcurve[:,1])
    stddev = (baseline_lightcurve[:,1] - median_mag).std()

    idx1 = np.where(event_lightcurve[:,1] < median_mag + 3.0*stddev)[0]

    # Identify those datapoints within the event
    idx2 = np.where(event_lightcurve[:,0] >= lcevent.start_time)[0]
    idx3 = np.where(event_lightcurve[:,0] <= lcevent.start_time + lcevent.duration)[0]
    idx4 = set(idx2).intersection(set(idx3))
    idx = list(idx4.intersection(set(idx1)))

    # Identify groups of consecutive datapoints, and find the length of the
    # group with the most entries
    npoints = 0
    if len(idx) > 0:
        groups = np.split(idx, np.where(np.diff(idx) != 1)[0] + 1)
        npoints = np.array([len(entry) for entry in groups]).max()

    return npoints

def second_peak_diagnostics(e, event_list):

    # Check to see if there is more than one event associated with this target
    if len(event_list) > 1:

        # Identify the nearest event to this one in the list
        mid_event = e.start_time + e.duration/2.0
        delta_mid_event_times = np.array(
            [(et.start_time + et.duration/2.0)-mid_event for et in event_list if e != et]
        )
        et_idx = np.argmin(delta_mid_event_times)

        # Time to nearest other peak
        Event.objects.filter(pk=e.pk).update(time_to_second_peak=delta_mid_event_times[et_idx])

        # Second peak mag
        other_events = [et for et in event_list if e != et]
        Event.objects.filter(pk=e.pk).update(second_peak_mag=other_events[et_idx].peak_mag)

def link_events(events_qs, plot=False):
    """
    Function to perform a cluster analysis on all Events in [RA, Dec, time] space,
    following the approach by Will DeRocco.

    All events linked to a cluster will record the number of members in that cluster
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
    for i,e in enumerate(events_list):
        event_cluster = cluster[i] - 1  # Offset for Python array indexing
        nlinked = len(clusters[event_cluster]) - 1  # Exclude the current event from the total
        Event.objects.filter(pk=e.pk).update(Nlinked_events=nlinked)
