import django
from django.db import connections
from django.core.management.base import BaseCommand, CommandError
from concurrent.futures import ProcessPoolExecutor, as_completed
from os import path
import json
import glob
import time
from datetime import datetime, UTC
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

def wait_for_tasks(since, timeout, poll_seconds=5):
    """
    Wait for the background tasks queued since a time to finish (to succeed or to fail). Saving the
    sources and events of an ingest queues tasks (the source diagnostics, the event's thumbnail, the
    search for moving objects), which the db_worker does after the ingest itself is done. A batch
    isn't complete until they are, as what they make is part of what the batch brings.

    Models are imported here, not at the top, for the reason given in ingest_alert_and_model_event.

    :param since: datetime, the tasks queued from this time are waited for
    :param timeout: seconds to wait, at most
    :param poll_seconds: seconds between looks at the queue
    :returns: the number of tasks not finished when this stopped waiting; 0 if all were
    """
    from django_tasks.backends.database.models import DBTaskResult
    from django_tasks.task import ResultStatus

    deadline = time.monotonic() + timeout
    while True:
        unfinished = DBTaskResult.objects.filter(enqueued_at__gte=since).exclude(
            status__in=[ResultStatus.SUCCEEDED, ResultStatus.FAILED]
        ).count()
        if unfinished == 0 or time.monotonic() >= deadline:
            return unfinished

        logger.info('Waiting for ' + str(unfinished) + ' background tasks queued by this ingest')
        time.sleep(poll_seconds)

class Command(BaseCommand):
    help = 'Tool to ingest and model a set of alerts'

    def add_arguments(self, parser):
        parser.add_argument('data_dir', help='Path to the directory of JSON catalog files')
        parser.add_argument(
            '--max-workers', type=int, default=5,
            help='Number of fitting processes to run in parallel (default: 5)'
        )
        parser.add_argument(
            '--task-timeout', type=int, default=1800,
            help='Seconds to wait, once the alerts are ingested, for the background tasks they queued '
                 '(source diagnostics, thumbnails; done by db_worker) to finish. The batch is complete '
                 'only when they have; if they haven\'t by then it is marked failed (default: 1800)'
        )

    def handle(self, *args, **options):

        from custom_code.models import AlertIngest

        if not path.isdir(options['data_dir']):
            raise IOError('Cannot find input data directory ' + options['data_dir'])

        ts = datetime.now(UTC)
        batch_id = 'ingest_' + ts.strftime('%Y-%m-%dT%H:%M:%S')
        batch = AlertIngest.objects.create(
            batch_id=batch_id,
            started_at=ts,
            status=AlertIngest.OperationalStatus.running,
        )

        # The batch is Running until it has been done to the end: whatever stops it, it must not be
        # left looking as if it were still going
        try:
            self.ingest_all(options, ts)
        except BaseException:
            AlertIngest.objects.filter(pk=batch.pk).update(status=AlertIngest.OperationalStatus.failed)
            logger.error('Alert ingest ' + batch_id + ' failed')
            raise

        AlertIngest.objects.filter(pk=batch.pk).update(
            status=AlertIngest.OperationalStatus.complete, completed_at=datetime.now(UTC)
        )
        logger.info('Alert ingest completed')

    def ingest_all(self, options, started_at):
        """Ingest and model every alert file of the directory, then wait for the tasks they queued"""

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

        unfinished = wait_for_tasks(started_at, options['task_timeout'])
        if unfinished:
            raise CommandError(
                str(unfinished) + ' background tasks queued by this ingest have not finished after '
                + str(options['task_timeout']) + ' s. Is db_worker running?'
            )
