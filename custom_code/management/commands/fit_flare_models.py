from django.core.management.base import BaseCommand
from custom_code.models import Event
from tom_targets.models import Target
from custom_code.management.commands import data_utils
from custom_code import flare_fit_functions

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
            davenport_results = flare_fit_functions.run_davenport_flare_fit(event)
            davenport_flare = data_utils.store_davenportflare_model_parameters(
                event, davenport_results
            )
            data_utils.store_model_lightcurve(event, davenport_results, 'davenport_flare')

            # Pitkin flare model fit
            pitkin_results = flare_fit_functions.run_pitkin_flare_model_fit(event)
            pitkin_flare = data_utils.store_pitkinflare_model_parameters(
                event, pitkin_results
            )
            data_utils.store_model_lightcurve(event, pitkin_results, 'pitkin_flare')
