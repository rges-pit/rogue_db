from django_tasks import task
from .target_models import RogueTarget
from .variable_stars import find_nearest_rges_variable_catalog

@task
def check_target_for_variable_star(target_id):
    target = RogueTarget.objects.get(pk=target_id)
    find_nearest_rges_variable_catalog(target)