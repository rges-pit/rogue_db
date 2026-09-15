from django.core.management.base import BaseCommand
from custom_code.models import VariableStar
from astropy.coordinates import SkyCoord
from astropy import units as u
import pandas as pd

class Command(BaseCommand):
    help = 'Tool to ingest the MOA catalog of known flare stars'

    def add_arguments(self, parser):
        parser.add_argument('catalog_path', help='Path to the CSV catalog file')

    def handle(self, *args, **options):

        # Load the catalog
        df = pd.read_csv(options['catalog_path'])

        # Build list of VariableStar entries for ingest
        entries = []
        for flare in df.itertuples():
            s = SkyCoord(flare.RA, flare.DEC, frame='icrs', unit=(u.hourangle, u.deg))
            entries.append(VariableStar(
                ra=s.ra.deg, dec=s.dec.deg, type='flare',
                moa_id='MOA_flare_'+str(flare.Index))
            )

        # Bulk ingest
        created_entries = VariableStar.objects.bulk_create(entries)
