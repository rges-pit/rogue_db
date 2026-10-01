from django.core.management.base import BaseCommand
from custom_code.models import Event
from custom_code import variable_stars
from custom_code import serializers, data_utils
from tom_targets.models import Target
from django.db.models import F

class Command(BaseCommand):
    help = 'Tool to facilitate manual edits of the database'

    #def add_arguments(self, parser):
     #   parser.add_argument('data_dir', help='Path to the directory of JSON catalog files')

    def handle(self, *args, **options):

        #updated = Event.objects.update(duration=F('duration') * 2)
        #updated = Target.objects.update(mag_now_passband='Roman F146')
        #print(f'Updated {updated} targets')
        #qs = Target.objects.all()
        #for t in qs:
        #    variable_stars.calc_periodogram(t)
        qs = Event.objects.all()
        for e in qs:
            datasets = data_utils.get_reduced_data(e, source_name='Roman_F146')
            lightcurve = data_utils.fetch_lightcurve(datasets)
            peak_mag = serializers.estimate_peak_mag(e, lightcurve)
            Event.objects.filter(pk=e.pk).update(peak_mag=peak_mag)