from django.core.management.base import BaseCommand
from custom_code.models import Event
from tom_targets.models import Target
from custom_code.management.commands import data_utils
from custom_code import pylima_fit_functions
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fit a selected event with PSPL models, and ingest the fit results'

    def add_arguments(self, parser):
        parser.add_argument('source_name', help='Source name')

    def handle(self, *args, **options):

        # Find the most recent event associated with the requested target.
        target = Target.objects.get(name=options['source_name'])
        event = Event.objects.filter(target=target).order_by('-start_time')[0]

        if event:
            pylima_results = pylima_fit_functions.run_fit(event, bandpass='Roman_F146', verbose=True)

            # Store model lightcurves
            if pylima_results['model_telescope_pspl']:
                data_utils.store_model_lightcurve(event, pylima_results, 'pspl')
                logger.info('Stored PSPL model lightcurve for event ' + event.target.name)
            else:
                logger.warning('No valid PSPL produced so no model lightcurve for event ' + event.target.name)

            if pylima_results['model_telescope_fspl']:
                data_utils.store_model_lightcurve(event, pylima_results, 'fspl')
                logger.info('Stored FSPL model lightcurve for event ' + event.target.name)
            else:
                logger.warning('No valid FSPL produced so no model lightcurve for event ' + event.target.name)

            # Store model parameters
            data_utils.store_microlensing_model_parameters(event, pylima_results)

        else:
            logger.warning('Found no database entry for ' + options['target_name'])
