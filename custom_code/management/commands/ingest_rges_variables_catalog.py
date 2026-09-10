from django.core.management.base import BaseCommand
from custom_code.models import VariableStar
from os import path
import json

class Command(BaseCommand):
    help = 'Tool to ingest the RGES-PIT catalog of variable stars'

    def add_arguments(self, parser):
        parser.add_argument('catalog_path', help='Path to the JSON catalog file')

    def handle(self, *args, **options):

        # Load the variable star catalog, parsing the entries so as to
        # produce the parameter set expected by the database model
        variable_stars = self.parse_json_catalog(options)

        # Build list of VariableStar entries for ingest
        entries = [
            VariableStar(**vstar)
            for vstar in variable_stars
        ]

        # Bulk ingest
        created_entries = VariableStar.objects.bulk_create(entries)

    def parse_json_catalog(self, options):
        """
        Load the RGES-PIT variable star catalog in JSON format
        """

        if not path.isfile(options['catalog_path']):
            raise IOError('Cannot find input catalog ' + options['catalog_path'])

        with open(options['catalog_path'], "r") as infile:
            json_object = json.loads(infile.read())

        # Parameters: ra, dec, ogle_id, vvv_id, gaia_id, type
        variable_stars = []
        for name, params in json_object.items():
            vstar = {
                'ra': None, 'dec': None,
                'ogle_id': None, 'vvv_id': None, 'gaia_id': None,
                'type': None
            }
            if 'OGLE-' in name:
                vstar['ogle_id'] = name
            vstar['vvv_id'] = params['VVV_ID']
            vstar['gaia_id'] = params['Gaia_ID']
            vstar['type'] = params['Type']
            vstar['ra'] = params['RA']
            vstar['dec'] = params['Dec']
            variable_stars.append(vstar)

        return variable_stars