import logging
from concurrent.futures import ProcessPoolExecutor, as_completed

import django
from django.core.management.base import BaseCommand
from django.db import connections
from django.db.models import Q
from astropy.time import Time
from custom_code import event_functions

logger = logging.getLogger(__name__)


def _init_worker():
    """
    Runs once in each worker process before it handles any tasks.

    A worker process started via ``multiprocessing``'s ``spawn`` method (the
    default on macOS/Windows) is a fresh interpreter with no initialized
    Django app registry, so importing Django models before this runs would
    raise AppRegistryNotReady. Also drops any DB connection the process might
    have inherited from the parent (relevant under ``fork``, the Linux
    default) -- connections must never be shared across processes, so each
    worker opens its own the next time it touches the DB.
    """
    django.setup()
    connections.close_all()


def fit_target(target_pk):
    """
    Fit a single target's photometry with a microlensing model and store the
    results. Runs in a worker process.

    Imports of Django models are deferred to inside this function (and
    _init_worker above), rather than at module level, so that unpickling this
    function in a freshly spawned worker doesn't trigger those imports before
    _init_worker's django.setup() call has run.

    :param target_pk: primary key of the Target to fit.
    :returns: (target_pk, target_name_or_None, success, error_message_or_None)
    """
    from tom_targets.models import Target
    from custom_code.models import Event

    try:
        target = Target.objects.get(pk=target_pk)
        events = Event.objects.filter(target=target).order_by('-start_time')
    except Target.DoesNotExist:
        return target_pk, None, False, 'Target no longer exists'

    if events.count() > 0:
        for e in events:
            try:
                event_functions.run_event_modeling(e)

                return target_pk, target.name, True, None

            except Exception as e:
                logger.exception('Fit failed for event ' + target.name)
                return target_pk, target.name, False, str(e)

    return target_pk, target.name, False, 'No events found for this target'


class Command(BaseCommand):
    help = 'Fit all FFP candidates with microlensing models, in parallel'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-workers', type=int, default=5,
            help='Number of fitting processes to run in parallel (default: 5)'
        )

    def handle(self, *args, **options):
        from tom_targets.models import Target
        from custom_code.models import Event
        from custom_code import diagnostics

        max_workers = options['max_workers']

        # First perform a cluster analysis on all known Events in order to identify
        # clusters in RA, Dec and time
        events_list = Event.objects.all()
        diagnostics.link_events(events_list, plot=False)

        # Retrieve a list of Targets classified as microlensing candidates with t0 within the last
        # week.  Each Target has a last_fit parameter which has a default (i.e. unmodeled) value of
        # 2446756.50000.  In addition to unmodeled Targets, we also want to include those whose
        # prior models indicate that 1.5d < current_time - t0 < 2.5d and 6.5d < current_time - t0 < 7.5d
        current_jd = Time.now().jd
        qs = Target.objects.filter(
            Q(last_fit=2446756.50000)
            | Q(t0__gte=current_jd - 2.5, t0__lte=current_jd - 1.5)
            | Q(t0__gte=current_jd - 7.5, t0__lte=current_jd - 6.5)
        )

        target_pks = list(qs.values_list('pk', flat=True))
        logger.info('Fitting ' + str(len(target_pks)) + ' targets with up to ' + str(max_workers) + ' parallel workers')

        if not target_pks:
            logger.info('No targets need fitting')
            return

        # Release this process's DB connection before spawning workers;
        # connections must never be shared across processes.
        connections.close_all()

        succeeded = []
        failed = []

        with ProcessPoolExecutor(max_workers=max_workers, initializer=_init_worker) as executor:
            futures = {executor.submit(fit_target, pk): pk for pk in target_pks}

            for future in as_completed(futures):
                pk = futures[future]
                try:
                    _, name, success, error = future.result()
                except Exception as e:
                    logger.exception('Worker process crashed while fitting target pk= ' + str(pk))
                    failed.append((pk, str(e)))
                    continue

                if success:
                    succeeded.append(name)
                    logger.info('Completed fit for ' + name)
                else:
                    failed.append((name or pk, error))
                    logger.error(f'Failed fit for {name or pk}: {error}')

        logger.info('Finished: ' + str(len(succeeded)) + ' succeeded, ' + str(len(failed)) + ' failed')
        for name, error in failed:
            logger.error(f'  {name}: {error}')
