from django.db.models.signals import post_save
from django.dispatch import receiver

from .target_models import RogueTarget
from .tasks import check_target_for_variable_star

@receiver(post_save, sender=RogueTarget)
def on_target_saved(sender, instance, created, update_fields, **kwargs):

    # Catch incomplete field set
    if update_fields and set(update_fields) <= {'nearest_variable_star', 'angular_separation_variable'}:
        return

    # update_fields is None if a full .save() of a target is done, including creation.
    # This ensures the function does nothing except in cases where the ra, dec of the
    # target will actually change
    if update_fields is not None and not ({'ra', 'dec'} & set(update_fields)):
        return

    check_target_for_variable_star.enqueue(instance.pk)