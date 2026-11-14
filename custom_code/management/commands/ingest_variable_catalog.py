from django.core.management.base import BaseCommand
from custom_code.models import VariableStar
from custom_code import variable_stars
import numpy as np
from os import path
from astropy.coordinates import SkyCoord
from astropy import units as u

class Command(BaseCommand):
    help = 'Tool to ingest the RGES-PIT catalog of variable stars'

    def add_arguments(self, parser):
        parser.add_argument('catalog_path', help='Path to the ASCII catalog file')
        parser.add_argument('format', help='Catalog format {MOA, OGLE}')

    def handle(self, *args, **options):

        # Position matching threshold
        radius = 2.0 / 3600.0  # Degrees

        # Extract from the DB lists of existing known variables and their coordinates
        # for de-duplification
        existing_var_names = variable_stars.known_variable_names()
        existing_var_positions, existing_var_pks = variable_stars.known_variable_positions()

        # Load the variable star catalog, parsing the entries so as to
        # produce the parameter set expected by the database model
        if str(options['format']).upper() == 'MOA':
            use_id = 'moa_id'   # ID in the table to identify with
            catalog_entries = self.parse_moa_catalog(options)

        # Review the new catalog entries, comparing them with those in the database
        # to avoid duplication
        new_variables = []
        for vstar in catalog_entries:
            duplicate = False
            s = SkyCoord(vstar['ra'], vstar['dec'], frame='icrs', unit=(u.deg, u.deg))

            # First check for an existing variable of the same name
            if vstar[use_id] in existing_var_names:
                duplicate = True

            # Next do a cone search
            if not duplicate:
                sep = s.separation(existing_var_positions)
                idx = np.where(sep < radius * u.deg)[0]
                if len(idx) > 0:
                    idx = np.argsort(sep)
                    var_pk = existing_var_pks[idx]
                    duplicate = True
                    if str(options['format']).upper() == 'MOA':
                        VariableStar.objects.filter(pk=var_pk).update(mod_ia=vstar['moa_id'])

                    # ELSE HANDLE OGLE

            if not duplicate:
                new_variables.append(vstar)

        # Ingest any new variables
        #created_entries = VariableStar.objects.bulk_create(new_variables)

    def parse_moa_catalog(self, options):
        """
        Method to parse variable star coordinates from a MOA-style catalog
        Expects ASCII format data with columns:
        Identifier  designation  RA(sexig)  Dec(sexig)  Comment
        """

        # The catalog has to be scanned for duplicates within itself.
        # Since stars can be detected multiple times in the same survey, name-matching is
        # unreliable, so we use a cone search
        radius = 2.0 / 3600.0 * u.deg

        catalog_entries = []
        with open(options['catalog_path'], 'r') as f:
            line_list = f.readlines()

            ras = []
            decs = []
            for line in line_list:
                entries = line.replace('\n','').split()
                s = SkyCoord(entries[2], entries[3], frame='icrs', unit=(u.hourangle, u.deg))
                type = ' '.join(entries[4:])

                # Check this isn't a duplicate of another one in the same catalog
                vars = SkyCoord(ras, decs, frame='icrs', unit=(u.deg, u.deg))
                sep = s.separation(vars)
                idx = np.where(sep < radius)[0]
                if len(idx) == 0:
                    vstar = {
                        'moa_id': entries[0],
                        'ra': s.ra.deg,
                        'dec': s.dec.deg,
                        'ogle_id': None, 'vvv_id': None, 'gaia_id': None,
                        'type': type
                    }
                    catalog_entries.append(vstar)
                ras.append(s.ra.deg)
                decs.append(s.dec.deg)

        return catalog_entries
