from django.core.management.base import BaseCommand
from django.db.utils import IntegrityError
from custom_code.serializers import MSOSAlertSerializer
from os import path
import json
import glob

class Command(BaseCommand):
    help = 'Tool to ingest the RGES-PIT catalog of variable stars'

    def add_arguments(self, parser):
        parser.add_argument('data_dir', help='Path to the directory of JSON catalog files')

    def handle(self, *args, **options):

        if not path.isdir(options['data_dir']):
            raise IOError('Cannot find input data directory ' + options['data_dir'])

        file_list = glob.glob(path.join(options['data_dir'], '*.json'))

        for file_path in file_list:
            with open(file_path, 'r') as file:
                data = json.load(file)

                alert = MSOSAlertSerializer(data=data)
                alert.is_valid(raise_exception=True)
                try:
                    alert.save()
                    self.stdout.write(self.style.SUCCESS(f'Ingested {file_path}'))
                except IntegrityError:
                    print('Duplicate alert not ingested')

