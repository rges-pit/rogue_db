import django
from django.db import connections
from django.core.management.base import BaseCommand
from concurrent.futures import ProcessPoolExecutor, as_completed
from os import path
import json
import glob
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def _init_worker():
    """
    Initialize worker instance for parallelized ingest
    """
    django.setup()
    connections.close_all()

def ingest_alert_and_model_event(alert_file):
    """
    Function to ingest an alert and perform full modeling suite for a single event
    """

    # Imported here, because this needs to happen separately for
    # each parallel worker
    from custom_code.serializers import MSOSAlertSerializer
    from custom_code import event_functions

    with open(alert_file, 'r') as file:
        data = json.load(file)
        logger.info('Received alert ' + path.basename(alert_file))

        # Parse the alert packet and create all necessary Targets, Events and RGESAlerts.
        # An alert that has been ingested before isn't an error: the serializer finds the rows it made
        # then (and stores only the photometry that is new), and the event is modeled again. An error
        # here is a failure of the ingest, which rolls it back whole: there is no event to model, so
        # it's left to fail this alert, and to be reported with the others at the end of the run.
        serial = MSOSAlertSerializer(data=data)
        serial.is_valid(raise_exception=True)
        serial.save()
        logger.info('Completed alert ingest')

        # Now fit the standard set of models to the event
        event_functions.run_event_modeling(serial.event)

        logger.info('Completed ingest of alert ' + path.basename(alert_file))

    return True

class Command(BaseCommand):
    help = 'Tool to ingest and model a set of alerts'

    def add_arguments(self, parser):
        parser.add_argument('data_dir', help='Path to the directory of JSON catalog files')
        parser.add_argument(
            '--max-workers', type=int, default=5,
            help='Number of fitting processes to run in parallel (default: 5)'
        )

    def handle(self, *args, **options):

        if not path.isdir(options['data_dir']):
            raise IOError('Cannot find input data directory ' + options['data_dir'])

        max_workers = options['max_workers']

        file_list = glob.glob(path.join(options['data_dir'], '*.json'))

        succeeded = []
        failed = []

        with ProcessPoolExecutor(max_workers=max_workers, initializer=_init_worker) as executor:
            futures = {
                executor.submit(ingest_alert_and_model_event, alert_file): alert_file for alert_file in file_list
            }

            for future in as_completed(futures):
                alert_file = futures[future]
                file_name = path.basename(alert_file)
                try:
                    status = future.result()
                except Exception as e:
                    logger.exception('Worker process crashed while ingesting alert file: ' + str(alert_file))
                    failed.append((file_name, str(e)))
                    continue

                if status:
                    succeeded.append(file_name)
                    logger.info('Completed fit for ' + file_name)

        logger.info('Finished: ' + str(len(succeeded)) + ' succeeded, ' + str(len(failed)) + ' failed')
        for file_name, error in failed:
            logger.error(file_name + ': ' + str(error))

        logger.info('Alert ingest completed')
