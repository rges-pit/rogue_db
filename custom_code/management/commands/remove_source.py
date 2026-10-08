from django.core.management.base import BaseCommand
from tom_targets.models import Target
from custom_code.models import RGESAlert, Event, EventModel

class Command(BaseCommand):
    help = 'Tool to delete a source and all associated alerts, events and event models'

    def add_arguments(self, parser):
        parser.add_argument('source_name', help='Name of the source to remove')

    def handle(self, *args, **options):

        t = Target.objects.get(name=options['source_name'])

        if t:
            events = Event.objects.filter(target=t)
            alerts = RGESAlert.objects.filter(event__in=events)
            eventmodels = EventModel.objects.filter(event__in=events)

            print('Removing 1 target with ' + str(events.count()) + ' events, '
                  + str(alerts.count()) + ' alerts and ' + str(eventmodels.count()) + ' event models')

            # Delete in order of reverse foreign key relationships to avoid orphans
            deleted_alerts_count, details = alerts.delete()
            deleted_eventmodels_count, details = eventmodels.delete()
            deleted_events_count, details = events.delete()
            deleted_target_count, details = t.delete()
