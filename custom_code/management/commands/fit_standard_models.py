from django.core.management.base import BaseCommand
from custom_code.models import Event
from tom_targets.models import Target
from custom_code.management.commands import general_fit_functions, data_utils

import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fit a selected event general polynomial models, and ingest the fit results'

    def add_arguments(self, parser):
        parser.add_argument('source_name', help='Source name')

    def handle(self, *args, **options):

        # Find the most recent event associated with the requested target.
        target = Target.objects.get(name=options['source_name'])
        event = Event.objects.filter(target=target).order_by('-window_end')[0]

        # If a latest event is found, perform the model fits and store the parameters
        if event:
            # Straight line model fit
            results = general_fit_functions.run_straightline_fit(event)
            data_utils.store_straightline_model_parameters(event, results)

            # TO DO: Skew normal model fit
            
            logger.info('Completed standard model fits for ' + options['target_name'])

        else:
            logger.warning('Found no database entry for ' + options['target_name'])