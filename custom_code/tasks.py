from django_tasks import task
from .target_models import RogueTarget
from .source_functions import run_source_diagnostics
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
def compute_source_diagnostics(target_id):
    target = get_or_skip(RogueTarget, target_id, 'compute_source_diagnostics')
    if target is not None:
        run_source_diagnostics(target)
