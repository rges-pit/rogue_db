import logging

from django.core.management.base import BaseCommand, CommandError

from custom_code import diagnostics, event_functions
from custom_code.models import Event
from tom_targets.models import Target

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Model one event, as model_events does for every target: a new modeling process, which fits '
        'all of the models and records the diagnostics, and leaves those of earlier processes as they were'
    )

    def add_arguments(self, parser):
        parser.add_argument('source_name', help='Source name')
        parser.add_argument(
            '--event-id', help="ID of the event to model (default: the source's most recent event)"
        )

    def handle(self, *args, **options):
        try:
            target = Target.objects.get(name=options['source_name'])
        except Target.DoesNotExist:
            raise CommandError('No source named ' + options['source_name'])

        events = Event.objects.filter(target=target)
        if options['event_id']:
            events = events.filter(event_id=options['event_id'])
        event = events.order_by('-start_time').first()
        if event is None:
            raise CommandError('No event found for ' + options['source_name'])

        # Each event is linked to others in the cluster analysis of all the events, which the
        # modeling records with the rest of its diagnostics
        linked_events = diagnostics.link_events(Event.objects.all())

        event_functions.run_event_modeling(event, linked_events.get(event.pk))
        self.stdout.write('Modeled ' + target.name + ', event ' + str(event.event_id))
