from django.core.management.base import BaseCommand
from custom_code.models import Event
from django.db.models import F

class Command(BaseCommand):
    help = 'Tool to facilitate manual edits of the database'

    #def add_arguments(self, parser):
     #   parser.add_argument('data_dir', help='Path to the directory of JSON catalog files')

    def handle(self, *args, **options):

        updated = Event.objects.update(duration=F('duration') * 2)
        print(f'Updated {updated} events')