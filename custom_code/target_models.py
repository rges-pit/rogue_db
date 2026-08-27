from django.db import models

from tom_targets.models import BaseTarget

# Create your models here.
class RogueTarget(BaseTarget):
    """
    Custom Target model including attributes describing candidate objectss
    """

    # Microlensing-specific fields
    classification = models.CharField(max_length=50, default='Microlensing PSPL')
    category = models.CharField(max_length=50, default='Microlensing stellar/planet')
    t0 = models.FloatField(default=0)
    t0_error = models.FloatField(default=0)
    u0 = models.FloatField(default=0)
    u0_error = models.FloatField(default=0)
    tE = models.FloatField(default=0)
    tE_error = models.FloatField(default=0)
    piEN = models.FloatField(default=0)
    piEN_error = models.FloatField(default=0)
    piEE = models.FloatField(default=0)
    piEE_error = models.FloatField(default=0)
    rho = models.FloatField(default=0)
    rho_error = models.FloatField(default=0)
    s = models.FloatField(default=0)
    s_error = models.FloatField(default=0)
    q = models.FloatField(default=0)
    q_error = models.FloatField(default=0)
    alpha = models.FloatField(default=0)
    alpha_error = models.FloatField(default=0)
    source_magnitude = models.FloatField(default=0)
    source_mag_error = models.FloatField(default=0)
    blend_magnitude = models.FloatField(default=0)
    blend_mag_error = models.FloatField(default=0)
    baseline_magnitude = models.FloatField(default=0)
    baseline_mag_error = models.FloatField(default=0)
    last_fit = models.FloatField(default=2446756.50000)
    chi2 = models.FloatField(default=99999.9999)
    red_chi2 = models.FloatField(default=99999.9999)
    ks_test = models.FloatField(default=0)
    sw_test = models.FloatField(default=0)
    ad_test = models.FloatField(default=0)
    mag_now = models.FloatField(default=0)
    mag_now_passband = models.CharField(max_length=10, default='', null=True, blank=True)

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

