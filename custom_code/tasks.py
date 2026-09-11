from django_tasks import task
from .target_models import RogueTarget
from custom_code.models import Event
from .variable_stars import find_nearest_rges_variable_catalog
from .solar_system import find_moving_objects_near_event

@task
def check_target_for_variable_star(target_id):
    target = RogueTarget.objects.get(pk=target_id)
    find_nearest_rges_variable_catalog(target)

@task
def check_event_for_moving_objects(event_id):
    event = Event.objects.get(pk=event_id)
    find_moving_objects_near_event(event)