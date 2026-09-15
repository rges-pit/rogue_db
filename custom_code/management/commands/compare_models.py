from django.core.management.base import BaseCommand
from tom_targets.models import Target
from custom_code.models import (
    Event, StraightLineModel, PSPLModel, FSPLModel, DavenportFlareModel, PitkinFlareModel)
from custom_code import diagnostics

import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Compare the results of fitted models'

    def add_arguments(self, parser):
        parser.add_argument('source_name', help='Source name')

    def handle(self, *args, **options):

        # Find the most recent event associated with the requested target.
        target = Target.objects.get(name=options['source_name'])
        event = Event.objects.filter(target=target).order_by('-start_time')[0]

        # If a latest event is found, compare the models fitted
        if event:
            straight_line = StraightLineModel.objects.filter(
                event=event
            )
            pspl = PSPLModel.objects.filter(event=event)
            fspl = FSPLModel.objects.filter(event=event)
            davenport_flare = DavenportFlareModel.objects.filter(event=event)
            pitkin_flare = PitkinFlareModel.objects.filter(event=event)

            if straight_line.count() > 0 and pspl.count() > 0:
                diagnostics.compare_model_goodness_of_fit(event, pspl[0], straight_line[0])
            if straight_line.count() > 0 and fspl.count() > 0:
                diagnostics.compare_model_goodness_of_fit(event, fspl[0], straight_line[0])
            if pspl.count() > 0 and davenport_flare.count() > 0 and pitkin_flare.count() > 0:
                diagnostics.compare_model_goodness_of_fit(event, pspl[0], davenport_flare[0])
                diagnostics.compare_flare_models(event, pspl[0], davenport_flare[0], pitkin_flare[0])
            if fspl.count() > 0 and davenport_flare.count() > 0 and pitkin_flare.count() > 0:
                diagnostics.compare_flare_models(event, fspl[0], davenport_flare[0], pitkin_flare[0])
            logger.info('Stored goodness-of-fit diagnostics for ' + target.name)