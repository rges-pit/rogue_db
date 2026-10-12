import posixpath
import re

from django.core.management.base import BaseCommand, CommandError
from tom_targets.models import Target
from custom_code.models import RGESAlert, Event, EventModel, SourceDiagnostics

# The image files saved for a source's events and models, and what their names end with. They are
# written through their field's storage backend (local disk now, S3 later), so they're found and
# removed through it too, rather than by looking at the filesystem.
IMAGE_FIELDS = (
    ('thumbnail', Event._meta.get_field('thumbnail'), '_lc'),
    ('corner plot', EventModel._meta.get_field('corner_plot'), '_corner_plot'),
)


def walk(storage, path):
    """The names of all the files under a directory of a storage backend"""
    try:
        directories, files = storage.listdir(path)
    except FileNotFoundError:
        return
    for name in files:
        yield posixpath.join(path, name)
    for name in directories:
        yield from walk(storage, posixpath.join(path, name))


def find_image_files(field, ending, target, referenced):
    """
    The files of an image field belonging to a source: those the database refers to, and those
    left behind by earlier ingests of the source. Each ingest saves new files (the storage adds a
    random suffix to a name that's taken) and the database refers only to the latest, so most of a
    source's files belong to no row. They're recognised by their name, which starts with the
    source's name and ends with the given ending: <source>_..._lc.png, or ..._lc_<7 random
    characters>.png.

    :param referenced: the names of the files rows of the source refer to
    :returns: (the names of the files rows refer to, the names of the others)
    """
    directory = field.upload_to.split('/')[0]
    name = re.compile(rf'^{re.escape(target.name)}_.+{re.escape(ending)}(_[A-Za-z0-9]{{7}})?\.png$')
    leftover = {
        path for path in walk(field.storage, directory)
        if name.match(posixpath.basename(path))
    } - referenced

    return referenced, leftover


class Command(BaseCommand):
    help = ('Tool to delete a source and all associated alerts, events, event models, source '
            'diagnostics, event thumbnails and model corner plots')

    def add_arguments(self, parser):
        parser.add_argument('source_name', help='Name of the source to remove')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be removed, including the image files, and remove nothing'
        )

    def handle(self, *args, **options):

        try:
            t = Target.objects.get(name=options['source_name'])
        except Target.DoesNotExist:
            raise CommandError('No source named ' + options['source_name'])

        events = Event.objects.filter(target=t)
        sdiagnostics = SourceDiagnostics.objects.filter(target=t)
        alerts = RGESAlert.objects.filter(event__in=events)
        eventmodels = EventModel.objects.filter(event__in=events)

        # The files, found while the rows that refer to them are still there
        referenced_names = {
            'thumbnail': {event.thumbnail.name for event in events if event.thumbnail},
            'corner plot': {model.corner_plot.name for model in eventmodels if model.corner_plot},
        }
        files = {}
        for label, field, ending in IMAGE_FIELDS:
            used, leftover = find_image_files(field, ending, t, referenced_names[label])
            files[label] = (field.storage, used, leftover)

        summary = [
            str(len(used) + len(leftover)) + ' ' + label + ' files (' + str(len(used))
            + ' used by rows, ' + str(len(leftover)) + ' left by earlier ingests)'
            for label, (storage, used, leftover) in files.items()
        ]
        self.stdout.write(
            'Removing 1 target with ' + str(sdiagnostics.count()) + ' source diagnostics, '
            + str(events.count()) + ' events, '
            + str(alerts.count()) + ' alerts, ' + str(eventmodels.count()) + ' event models, '
            + ' and '.join(summary)
        )

        if options['dry_run']:
            for label, (storage, used, leftover) in files.items():
                for path in sorted(used | leftover):
                    self.stdout.write('  would remove ' + path)
            self.stdout.write('Dry run: nothing removed')
            return

        # Delete in order of reverse foreign key relationships to avoid orphans
        deleted_alerts_count, details = alerts.delete()
        deleted_diagnostics_count, details = sdiagnostics.delete()
        deleted_eventmodels_count, details = eventmodels.delete()
        deleted_events_count, details = events.delete()
        deleted_target_count, details = t.delete()

        # The files last, once the rows that refer to them are gone
        for label, (storage, used, leftover) in files.items():
            for path in sorted(used | leftover):
                storage.delete(path)
