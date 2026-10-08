from django.core.management.base import BaseCommand
from custom_code.models import SourceDiagnostics
from tom_targets.models import Target

class Command(BaseCommand):
    help = 'Tool to move parameters from the Target to a separate table'

    def handle(self, *args, **options):
        qs = Target.objects.all()
        for t in qs:
            s, created = SourceDiagnostics.objects.get_or_create(
                    target=t,
                    defaults=dict(
                        classification=t.classification,
                        category=t.category,
                        source_magnitude=t.source_magnitude,
                        source_mag_error=t.source_mag_error,
                        baseline_magnitude=t.baseline_magnitude,
                        baseline_mag_error=t.baseline_mag_error,
                        nearest_flare_star=t.nearest_flare_star,
                        angular_separation_flare_star=t.angular_separation_flare_star,
                        nearest_variable_star=t.nearest_variable_star,
                        angular_separation_variable=t.angular_separation_variable,
                        nearest_variable_type=t.nearest_variable_type,
                        max_peak_periodogram=t.max_peak_periodogram,
                        period=t.period
                    ),
                )
