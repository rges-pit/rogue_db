from django.db import models

from tom_targets.models import BaseTarget

# Create your models here.
class RogueTarget(BaseTarget):
    """
    Custom Target model including attributes describing candidate objectss
    """

    # Microlensing-specific fields
    mag_now = models.FloatField(default=0)
    mag_now_passband = models.CharField(max_length=10, default='', null=True, blank=True)
    periodogram = models.ImageField(upload_to='periodograms/%Y/%m/%d/', null=True, blank=True)

    class Meta:
        verbose_name = "target"
        permissions = (
            ('view_target', 'View Target'),
            ('add_target', 'Add Target'),
            ('change_target', 'Change Target'),
            ('delete_target', 'Delete Target')
        )

    def get_target_names(self, qs):
        """Attributes the names associated with this target"""
        self.targetnames = []
        for name in qs:
            self.targetnames.append(name.name)

    def get_target_name_survey(self, survey):
        """
        Method to identify the name for the current Target from a specific survey.
        Returns None if the survey has not detected the Target and hence there would be no name.
        Input:
            survey  str     Identifier used in Target names to distinguish detections from that survey, e.g.
                            'Gaia' or 'OGLE'

        Returns
            survey_name str Name string from the survey or None
        """

        survey_name = None

        # Check the primary name for the survey identifier
        if survey in self.name:
            survey_name = self.name

        # If not, check the aliases for the survey identifier:
        else:
            for tn in self.aliases.all():
                if survey in tn.name:
                    survey_name = tn.name

        return survey_name
