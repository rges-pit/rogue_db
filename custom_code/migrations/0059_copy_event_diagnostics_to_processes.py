from django.db import migrations
from django.db.models import OuterRef, Subquery

# The diagnostics that used to be columns on Event, and are now an EventDiagnostics row per modeling
# process
DIAGNOSTIC_FIELDS = [
    'peak_mag', 'time_to_second_peak', 'second_peak_mag', 'coverage_fraction', 'symmetry',
    'Npoint_above_3sigma',
    'delta_chi2_PSPL', 'delta_BIC_PSPL', 'delta_chi2_FSPL', 'delta_BIC_FSPL',
    'delta_chi2_PSPL_bestflare', 'delta_BIC_PSPL_bestflare',
    'delta_chi2_FSPL_bestflare', 'delta_BIC_FSPL_bestflare',
    'bestmulens_model_type', 'bestflare_model_type',
    'DIA_centroid_shift', 'PSF_centroid_shift', 'Nlinked_events',
    'nearest_moving_object', 'angular_separation_moving_object',
    'frac_below_baseline', 'max_excursion_below_baseline',
]
BATCH = 500


def events_to_processes(apps, schema_editor):
    """
    Until now an event held a single set of diagnostics and a modeling status, overwritten at each
    fit. Each event that has been through modeling (its status isn't Pending) becomes one
    ModelingProcess, with the status and time it had, one EventDiagnostics row with the values it had,
    and the models it already has. Events still Pending have nothing to keep and get no process.

    What the old fits were run with wasn't recorded, so their code_version says so.
    """
    Event = apps.get_model('custom_code', 'Event')
    EventModel = apps.get_model('custom_code', 'EventModel')
    ModelingProcess = apps.get_model('custom_code', 'ModelingProcess')
    EventDiagnostics = apps.get_model('custom_code', 'EventDiagnostics')

    # Rerunning shouldn't double up
    events = Event.objects.exclude(modeling_status='Pending').exclude(
        pk__in=ModelingProcess.objects.values('event')
    )

    for start in range(0, events.count(), BATCH):
        batch = list(events.order_by('pk')[start:start + BATCH])
        processes = ModelingProcess.objects.bulk_create([
            ModelingProcess(
                event=event,
                started_at=event.modeled_at or event.updated_at,
                completed_at=event.modeled_at,
                status=event.modeling_status,
                code_version='before-versioning',
            )
            for event in batch
        ])
        EventDiagnostics.objects.bulk_create([
            EventDiagnostics(
                process=process,
                **{name: getattr(event, name) for name in DIAGNOSTIC_FIELDS}
            )
            for event, process in zip(batch, processes)
        ])

    # The models these events already have belong to their process
    EventModel.objects.filter(process__isnull=True, event__isnull=False).update(
        process=Subquery(
            ModelingProcess.objects.filter(event=OuterRef('event')).order_by('-pk').values('pk')[:1]
        )
    )


def processes_to_events(apps, schema_editor):
    """
    Going back: an event gets the status and diagnostics of its latest process, which is what the
    old columns held. The earlier processes of an event that was modeled more than once are lost,
    as the old schema has nowhere to keep them.
    """
    Event = apps.get_model('custom_code', 'Event')
    EventDiagnostics = apps.get_model('custom_code', 'EventDiagnostics')

    for event in Event.objects.filter(modeling_processes__isnull=False).distinct().iterator():
        process = event.modeling_processes.order_by('-started_at', '-pk').first()
        values = {'modeling_status': process.status or 'Pending', 'modeled_at': process.completed_at}
        diagnostics = EventDiagnostics.objects.filter(process=process).first()
        if diagnostics:
            values.update({name: getattr(diagnostics, name) for name in DIAGNOSTIC_FIELDS})
        # update() rather than save(), so the event's updated_at isn't changed
        Event.objects.filter(pk=event.pk).update(**values)


class Migration(migrations.Migration):

    dependencies = [
        ('custom_code', '0058_versioned_modeling'),
    ]

    operations = [
        migrations.RunPython(events_to_processes, processes_to_events),
    ]
