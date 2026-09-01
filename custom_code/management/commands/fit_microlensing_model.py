from django.core.management.base import BaseCommand
from tom_targets.models import Target
from custom_code.management.commands import pylima_fit_functions, data_utils
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fit a selected event with PSPL models, and ingest the fit results'

    def add_arguments(self, parser):
        parser.add_argument('target_name', help='Event name')

    def handle(self, *args, **options):

        # Check if the selected event is known to the DB
        mulens = Target.objects.get(name=options['target_name'])

        if mulens:
            pylima_results = pylima_fit_functions.run_fit(mulens, verbose=False)

            # Store model lightcurve
            if pylima_results['model_telescope']:
                data_utils.store_model_lightcurve(mulens, pylima_results['model_telescope'])
                logger.info('Stored model lightcurve for event ' + mulens.name)
            else:
                logger.warning('No valid model fit produced so not model lightcurve for event ' + mulens.name)

            # Store model parameters
            data_utils.store_model_parameters(mulens, pylima_results)

        else:
            logger.warning('Found no database entry for ' + options['target_name'])
