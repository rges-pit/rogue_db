from django.db import migrations
from django.db.models import Exists, OuterRef, Subquery


def mark_modeled_events(apps, schema_editor):
    """
    The events that were modeled before an event had a modeling status were all given the default,
    Pending, which says they've yet to be modeled. Those with models stored are the ones that were
    modeled, so they're Complete, as of the last time one of their models was written. Events with no
    models are still waiting, and stay Pending.

    An event with only some of the models (from before a model type was added, say) is Complete too:
    there's no telling now whether the modeling stopped early, and refitting it brings it up to date.
    """
    Event = apps.get_model('custom_code', 'Event')
    EventModel = apps.get_model('custom_code', 'EventModel')

    models = EventModel.objects.filter(event=OuterRef('pk'))
    Event.objects.filter(Exists(models), modeling_status='Pending').update(
        modeling_status='Complete',
        modeled_at=Subquery(models.order_by('-updated_at').values('updated_at')[:1]),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('custom_code', '0056_alertingest_status'),
    ]

    operations = [
        # Nothing to undo: what the status was before is what it is made from
        migrations.RunPython(mark_modeled_events, migrations.RunPython.noop),
    ]
