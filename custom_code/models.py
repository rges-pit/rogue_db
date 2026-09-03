from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from .target_models import RogueTarget

class Event(models.Model):
    """
    An event is a feature in a source's lightcurve that occurs during a finite time window
    """
    target = models.ForeignKey(
        RogueTarget,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='events'
    )
    event_id = models.CharField(max_length=30, null=True, blank=True)
    window_start = models.FloatField(null=True, blank=True)
    window_end = models.FloatField(null=True, blank=True)

class RGESAlert(models.Model):
    """
    A discovery alert received from an RGES-PIT detection pipeline
    """

    class Classifications(models.TextChoices):
        microlensing = 'Microlensing', 'Microlensing'
        flare = 'Flare', 'Flare'
        variable_star = 'Variable star', 'Variable star'
        solar_system_object = 'Solar System object', 'Solar System object'
        other = 'Other', 'Other'
        unknown = 'Unknown', 'Unknown'

    class Passbands(models.TextChoices):
        F062 = 'F062', 'Roman F062'
        F087 = 'F087', 'Roman F087'
        F106 = 'F106', 'Roman F106'
        F129 = 'F129', 'Roman F129'
        F146 = 'F146', 'Roman F146'
        F158 = 'F158', 'Roman F158'
        F184 = 'F184', 'Roman F184'
        F213 = 'F213', 'Roman F213'
        Z = 'Z', 'Z'
        Y = 'Y', 'Y'
        J = 'J', 'J'
        H = 'H', 'H'
        Ks = 'Ks', 'Ks'
        B = 'B', 'Bessel B'
        V = 'V', 'Bessel V'
        R = 'R', 'Bessel R'
        I = 'I', 'Bessel I'
        u = 'u', 'SDSS u'
        g = 'g', 'SDSS g'
        r = 'r', 'SDSS r'
        i = 'i', 'SDSS i'
        z = 'z', 'SDSS z'
        y = 'y', 'SDSS y'
        unknown = 'unknown', 'Unknown'

    alert_id = models.IntegerField(default=0, null=True, blank=True)
    roman_id = models.CharField(max_length=100, verbose_name='Roman ID')
    event = models.ForeignKey(
        Event,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='alerts'
    )
    ra = models.FloatField(
        null=True, blank=True, verbose_name='Right Ascension', help_text='Right Ascension, in degrees.'
    )
    dec = models.FloatField(
        null=True, blank=True, verbose_name='Declination', help_text='Declination, in degrees.'
    )
    alert_neural_network_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Classification confidence as a percentage",
        null=True, blank=True
    )
    alert_delta_chi2 = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        help_text="Classification confidence in a delta chi2",
        null=True, blank=True
    )
    alert_classification = models.CharField(
        max_length=30,
        choices=Classifications.choices,
        default=Classifications.unknown,
        null=True
    )
    ffp_candidate = models.BooleanField(default=False)
    alert_origin = models.CharField(blank=True, null=True, max_length=60, verbose_name="Alert Origin")
    alert_notes = models.TextField(blank=True, null=True)
    alert_t0 = models.DecimalField(
        max_digits=13,
        decimal_places=5,
        validators=[MinValueValidator(2433282.5), MaxValueValidator(2470000.0)],
        help_text="Time of microlensing event peak as a Julian Date",
        null=True, blank=True
    )
    alert_tE = models.DecimalField(
        max_digits=10,
        decimal_places=5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1000.0)],
        help_text="Einstein crossing time of a microlensing event in days",
        null=True, blank=True
    )
    alert_u0 = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Impact parameter of a microlensing event",
        null=True, blank=True
    )
    alert_rho = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        validators=[MinValueValidator(0.0), MaxValueValidator(99.0)],
        help_text="Angular source size normalized by the angular Einstein radius of a microlensing event",
        null=True, blank=True
    )
    alert_peak_mag = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        validators=[MinValueValidator(-10.0), MaxValueValidator(30.0)],
        help_text="Peak brightness in magnitudes",
        null=True, blank=True
    )
    alert_baseline_mag = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        validators=[MinValueValidator(-10.0), MaxValueValidator(30.0)],
        help_text="Baseline brightness in magnitudes",
        null=True, blank=True
    )
    alert_mag_passband = models.CharField(
        max_length=15,
        default=Passbands.unknown,
        null=True
    )
    alert_timestamp = models.DateTimeField(blank=True, null=True)
    lightcurve_file = models.FileField(
        upload_to='uploads/%Y/%m/%d/',
        blank=True,
        null=True
    )
    alert_contents = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "rges_alert"
        permissions = (
            ('view_alert', 'View Alert'),
            ('add_alert', 'Add Alert'),
            ('change_alert', 'Change Alert'),
            ('delete_alert', 'Delete Alert'),
        )

class EventModel(models.Model):

    class ModelTypes(models.TextChoices):
        microlensing = 'Microlensing', 'Microlensing'
        flare = 'Flare', 'Flare'
        unknown = 'Unknown', 'Unknown'

    event = models.ForeignKey(
        Event,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='event_models'
    )
    
    model_type = models.CharField(
        max_length=15,
        choices=ModelTypes.choices,
        default=ModelTypes.unknown,
        null=True,
        blank=True,
        db_index=True
    )

    # Goodness of fit parameters
    chisq = models.FloatField(default=0, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class MicrolensingModel(EventModel):
    """
    Microlensing model parameters
    db_index=True on the base parameters (not their _error counterparts) since
    those are the fields TargetCutfileFilterSet filters on with min/max ranges.
    """
    model_category = models.CharField(max_length=30, null=True, blank=True)
    t0 = models.FloatField(default=0, null=True, blank=True, db_index=True)
    t0_error = models.FloatField(default=0, null=True, blank=True)
    u0 = models.FloatField(default=0, null=True, blank=True, db_index=True)
    u0_error = models.FloatField(default=0, null=True, blank=True)
    tE = models.FloatField(default=0, null=True, blank=True, db_index=True)
    tE_error = models.FloatField(default=0, null=True, blank=True)
    piEN = models.FloatField(default=0, null=True, blank=True, db_index=True)
    piEN_error = models.FloatField(default=0, null=True, blank=True)
    piEE = models.FloatField(default=0, null=True, blank=True, db_index=True)
    piEE_error = models.FloatField(default=0, null=True, blank=True)
    rho = models.FloatField(default=0, null=True, blank=True, db_index=True)
    rho_error = models.FloatField(default=0, null=True, blank=True)

class FlareModel(EventModel):
    """
    Flare model parameters
    """

    # Flare model parameters
    peak_amplitude = models.FloatField(default=0, null=True, blank=True, db_index=True)
    rise_time = models.FloatField(default=0, null=True, blank=True, db_index=True)
    tau1 = models.FloatField(default=0, null=True, blank=True, db_index=True)
    tau2 = models.FloatField(default=0, null=True, blank=True, db_index=True)
    equivalent_duration = models.FloatField(default=0, null=True, blank=True, db_index=True)
