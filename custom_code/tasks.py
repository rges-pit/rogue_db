from django_tasks import task
from .target_models import RogueTarget
from custom_code.models import Event
from .variable_stars import find_nearest_rges_variable_catalog, calc_periodogram
from .solar_system import find_moving_objects_near_event
from .event_functions import generate_event_lightcurves
import logging

logger = logging.getLogger(__name__)


def get_or_skip(model, pk, task_name):
    """
    Look up the row a task was queued for, or None if it has gone since: tasks run some time
    after the save that queued them, and the source (with its events) may have been removed in
    between. There's nothing left to do for a row that's gone, so the task should end quietly
    rather than fail.
    """
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        logger.info(f'{task_name}: {model.__name__} {pk} no longer exists, nothing to do')
    return obj

@task
def check_target_for_variable_star(target_id):
    target = get_or_skip(RogueTarget, target_id, 'check_target_for_variable_star')
    if target is not None:
        find_nearest_rges_variable_catalog(target)

@task
def compute_periodogram(target_id):
    target = get_or_skip(RogueTarget, target_id, 'compute_periodogram')
    if target is not None:
        calc_periodogram(target)

@task
def check_event_for_moving_objects(event_id):
    event = get_or_skip(Event, event_id, 'check_event_for_moving_objects')
    if event is not None:
        find_moving_objects_near_event(event)

@task
def make_event_lightcurve(event_id):
    event = get_or_skip(Event, event_id, 'make_event_lightcurve')
    if event is not None:
        generate_event_lightcurves(event)
