from django.core.management.base import BaseCommand
from custom_code.models import Event
from custom_code import event_functions

class Command(BaseCommand):
    help = 'Generate the lightcurve thumbnails for all events'

    def handle(self, *args, **options):
        events = Event.objects.all()

        for e in events:
            event_functions.generate_event_lightcurves(e)