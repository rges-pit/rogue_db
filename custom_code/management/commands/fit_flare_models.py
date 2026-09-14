from django.core.management.base import BaseCommand
from custom_code.models import Event
from tom_targets.models import Target
from custom_code.management.commands import flare_fit_functions
from custom_code.management.commands import data_utils

import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fit a selected event with flare models, and ingest the fit results'

    def add_arguments(self, parser):
        parser.add_argument('source_name', help='Source name')

    def handle(self, *args, **options):

        # Find the most recent event associated with the requested target.
        target = Target.objects.get(name=options['source_name'])
        event = Event.objects.filter(target=target).order_by('-start_time')[0]

        # If a latest event is found, perform the model fits and store the parameters
        if event:

            # Davenport flare model fit
            results = flare_fit_functions.run_davenport_flare_fit(event)

            # Store results
            if len(results) > 0:
                data_utils.store_davenportflare_model_parameters(event, results)