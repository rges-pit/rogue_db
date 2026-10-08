from django.core.management.base import BaseCommand
from django.db.utils import IntegrityError
from custom_code.serializers import MSOSAlertSerializer
from custom_code import event_functions
from os import path
import json
import glob
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class Command(BaseCommand):
    help = 'Tool to ingest and model a set of alerts'

    def add_arguments(self, parser):
        parser.add_argument('data_dir', help='Path to the directory of JSON catalog files')

    def handle(self, *args, **options):

        if not path.isdir(options['data_dir']):
            raise IOError('Cannot find input data directory ' + options['data_dir'])

        file_list = glob.glob(path.join(options['data_dir'], '*.json'))

        for file_path in file_list:
            with open(file_path, 'r') as file:
                data = json.load(file)
                logger.info('Received alert ' + path.basename(file_path))

                # Parse the alert packet and create all necessary Targets, Events and RGESAlerts
                # Then validated and check for duplication
                serial = MSOSAlertSerializer(data=data)
                serial.is_valid(raise_exception=True)
                try:
                    serial.save()
                    logger.info('Completed alert ingest')

                except IntegrityError:
                    logger.warning('Duplicate alert not ingested')

                # Now fit the standard set of models to the event
                event_functions.run_event_modeling(serial.event)

                logger.info('Completed ingest of alert ' + path.basename(file_path))

        logger.info('Alert ingest completed')
