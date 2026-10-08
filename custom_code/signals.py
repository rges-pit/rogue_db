from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .target_models import RogueTarget
from .models import Event
from .tasks import (check_target_for_variable_star, compute_periodogram,
                    check_event_for_moving_objects, make_event_lightcurve)

# What the tasks of each model are worked out from. They need queuing when a row is created,
# and when a save changes one of these; any other save leaves their results as they were.
TARGET_FIELDS = ('ra', 'dec')
EVENT_FIELDS = ('start_time', 'duration')


def saving_changes(instance, update_fields, fields):
    """
    Whether the save about to happen creates the row or changes any of the fields given.

    Compared with the stored row rather than the instance's own history: the instances the
    modeling code holds on to are saved over and over (the diagnostics each save the Event),
    and may be stale, so the values they hold say little about what a save changes.
    """
    if instance._state.adding:
        return True

    # A save limited to certain fields writes only those
    names = [name for name in fields if update_fields is None or name in update_fields]
    if not names:
        return False

    stored = type(instance).objects.filter(pk=instance.pk).values(*names).first()
    if stored is None:
        return True
    return any(stored[name] != getattr(instance, name) for name in names)


@receiver(pre_save, sender=RogueTarget)
def before_target_saved(sender, instance, update_fields, **kwargs):
    instance._queue_tasks = saving_changes(instance, update_fields, TARGET_FIELDS)

@receiver(post_save, sender=RogueTarget)
def on_target_saved(sender, instance, **kwargs):
    if getattr(instance, '_queue_tasks', True):
        check_target_for_variable_star.enqueue(instance.pk)
        compute_periodogram.enqueue(instance.pk)

@receiver(pre_save, sender=Event)
def before_event_saved(sender, instance, update_fields, **kwargs):
    instance._queue_tasks = saving_changes(instance, update_fields, EVENT_FIELDS)

@receiver(post_save, sender=Event)
def on_event_saved(sender, instance, **kwargs):
    if getattr(instance, '_queue_tasks', True):
        check_event_for_moving_objects.enqueue(instance.pk)
        make_event_lightcurve.enqueue(instance.pk)
