from django.core.management.base import BaseCommand
from custom_code.models import Event
from tom_targets.models import Target
from custom_code.management.commands import data_utils
from custom_code import general_fit_functions

import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fit a selected event general polynomial models, and ingest the fit results'

    def add_arguments(self, parser):
        parser.add_argument('source_name', help='Source name')

    def handle(self, *args, **options):

        # Find the most recent event associated with the requested target.
        target = Target.objects.get(name=options['source_name'])
        event = Event.objects.filter(target=target).order_by('-start_time')[0]

        # If a latest event is found, perform the model fits and store the parameters
        if event:
            # Straight line model fit
            straightline_results = general_fit_functions.run_event_straightline_fit(event)
            if len(straightline_results['coeffs']) > 0:
                straightline_model = data_utils.store_straightline_model_parameters(
                    event, straightline_results, 'Straight line'
                )
            data_utils.store_model_lightcurve(event, straightline_results, 'straight_line')

            # Baseline model fit
            baseline_results = general_fit_functions.run_baseline_fit(event)
            baseline_model = data_utils.store_straightline_model_parameters(
                event, baseline_results, 'Baseline'
            )
            data_utils.store_baseline_diagnostics(event, baseline_results)
            data_utils.store_model_lightcurve(event, baseline_results, 'baseline')

            # TO DO: Skew normal model fit

            logger.info('Completed standard model fits for ' + options['source_name'])

        else:
            logger.warning('Found no database entry for ' + options['source_name'])