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
    start_time = models.FloatField(null=True, blank=True)
    duration = models.FloatField(null=True, blank=True)
    time_to_second_peak = models.FloatField(null=True, blank=True)
    second_peak_mag = models.FloatField(null=True, blank=True)
    coverage_fraction = models.FloatField(null=True, blank=True)
    symmetry = models.FloatField(null=True, blank=True)
    Npoint_above_3sigma = models.FloatField(null=True, blank=True)
    delta_chi2_PSPL = models.FloatField(null=True, blank=True) # Relative to flat line
    delta_BIC_PSPL = models.FloatField(null=True, blank=True)
    delta_chi2_FSPL = models.FloatField(null=True, blank=True) # Relative to flat line
    delta_BIC_FSPL = models.FloatField(null=True, blank=True)
    delta_chi2_PSPL_bestflare = models.FloatField(null=True, blank=True)
    delta_BIC_PSPL_bestflare = models.FloatField(null=True, blank=True)
    delta_chi2_FSPL_bestflare = models.FloatField(null=True, blank=True)
    delta_BIC_FSPL_bestflare = models.FloatField(null=True, blank=True)
    DIA_centroid_shift = models.FloatField(null=True, blank=True)
    PSF_centroid_shift = models.FloatField(null=True, blank=True)
    Nlinked_events = models.IntegerField(default=0, null=True, blank=True)
    nearest_moving_object = models.CharField(max_length=60, null=True, blank=True)
    angular_separation_moving_object = models.FloatField(null=True, blank=True)
    frac_below_baseline = models.FloatField(null=True, blank=True)
    max_excursion_below_baseline = models.FloatField(null=True, blank=True)
    max_peak_periodogram = models.FloatField(null=True, blank=True)
    period = models.FloatField(null=True, blank=True)

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

    class AlertOrigin(models.TextChoices):
        aethra = 'aethra', 'Aethra'
        neural_network = 'neural network', 'Neural Network'
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
    alert_origin = models.CharField(
        max_length=60,
        choices=AlertOrigin.choices,
        default=AlertOrigin.unknown,
        blank=True,
        null=True,
        verbose_name="Alert Origin"
    )
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
        pspl = 'PSPL microlensing', 'PSPL microlensing'
        fspl = 'FSPL microlensing', 'FSPL microlensing'
        wide_bound_planet = 'Wide bound planet', 'Wide bound planet'
        davenport_flare = 'Davenport flare', 'Davenport flare'
        pitkin_flare = 'Pitkin flare', 'Pitkin flare'
        straightline = 'Straight line', 'Straight line'
        unknown = 'Unknown', 'Unknown'

    event = models.ForeignKey(
        Event,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='event_models'
    )
    
    model_type = models.CharField(
        max_length=60,
        choices=ModelTypes.choices,
        default=ModelTypes.unknown,
        null=True,
        blank=True,
        db_index=True
    )

    # Goodness of fit parameters
    chisq = models.FloatField(default=0, null=True, blank=True)
    BIC = models.FloatField(default=0, null=True, blank=True)
    fit_covariance = models.JSONField(default=dict, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class PSPLModel(EventModel):
    """
    Model parameters for a Point-Source, Point-Lens microlensing model
    """
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
    A = models.FloatField(default=0, null=True, blank=True, db_index=True)
    A_error = models.FloatField(default=0, null=True, blank=True)
    blend_parameters = models.JSONField(default=dict, null=True, blank=True)

class FSPLModel(EventModel):
    """
    Model parameters for a Finite-Source, Point-Lens microlensing model
    """
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
    A = models.FloatField(default=0, null=True, blank=True, db_index=True)
    A_error = models.FloatField(default=0, null=True, blank=True)
    blend_parameters = models.JSONField(default=dict, null=True, blank=True)

class WideBoundPlanetModel(EventModel):
    """
    Model parameters describing wide-orbit, but bound, planetary binary microlensing events
    """
    tc = models.FloatField(default=0, null=True, blank=True, db_index=True)
    tc_error = models.FloatField(default=0, null=True, blank=True)
    uc = models.FloatField(default=0, null=True, blank=True, db_index=True)
    uc_error = models.FloatField(default=0, null=True, blank=True)
    tE = models.FloatField(default=0, null=True, blank=True, db_index=True)
    tE_error = models.FloatField(default=0, null=True, blank=True)
    rho = models.FloatField(default=0, null=True, blank=True, db_index=True)
    rho_error = models.FloatField(default=0, null=True, blank=True)
    s = models.FloatField(default=0, null=True, blank=True, db_index=True)
    s_error = models.FloatField(default=0, null=True, blank=True)
    q = models.FloatField(default=0, null=True, blank=True, db_index=True)
    q_error = models.FloatField(default=0, null=True, blank=True)
    alpha = models.FloatField(default=0, null=True, blank=True, db_index=True)
    alpha_error = models.FloatField(default=0, null=True, blank=True)
    A = models.FloatField(default=0, null=True, blank=True, db_index=True)
    A_error = models.FloatField(default=0, null=True, blank=True)
    blend_parameters = models.JSONField(default=dict, null=True, blank=True)

class DavenportFlareModel(EventModel):
    """
    Model parameters for flare events as defined by Davenport et al. (2014), ApJ 797 122
    """
    t_peak = models.FloatField(default=0, null=True, blank=True, db_index=True)
    t_peak_error = models.FloatField(default=0, null=True, blank=True)
    peak_amplitude = models.FloatField(default=0, null=True, blank=True, db_index=True)
    peak_amplitude_error = models.FloatField(default=0, null=True, blank=True)
    t_FWHM = models.FloatField(default=0, null=True, blank=True, db_index=True)
    t_FWHM_error = models.FloatField(default=0, null=True, blank=True)

class PitkinFlareModel(EventModel):
    """
    Model parametrs for flare events as defined by Pitkin et al. (2014), MNRAS, 445, 3, 11
    """
    t_peak = models.FloatField(default=0, null=True, blank=True, db_index=True)
    t_peak_error = models.FloatField(default=0, null=True, blank=True)
    peak_amplitude = models.FloatField(default=0, null=True, blank=True, db_index=True)
    peak_amplitude_error = models.FloatField(default=0, null=True, blank=True)
    tau_gaussian_rise = models.FloatField(default=0, null=True, blank=True, db_index=True)
    tau_gaussian_rise_error = models.FloatField(default=0, null=True, blank=True)
    tau_exponential_decay = models.FloatField(default=0, null=True, blank=True, db_index=True)
    tau_exponential_decay_error = models.FloatField(default=0, null=True, blank=True)

class SkewNormalModel(EventModel):
    """
    Model parameters for a skew fit to the event lightcurve
    """
    t_peak = models.FloatField(default=0, null=True, blank=True, db_index=True)
    t_peak_error = models.FloatField(default=0, null=True, blank=True)
    peak_amplitude = models.FloatField(default=0, null=True, blank=True, db_index=True)
    peak_amplitude_error = models.FloatField(default=0, null=True, blank=True)
    omega = models.FloatField(default=0, null=True, blank=True, db_index=True)
    omega_error = models.FloatField(default=0, null=True, blank=True)
    alpha = models.FloatField(default=0, null=True, blank=True, db_index=True)
    alpha_error = models.FloatField(default=0, null=True, blank=True)

class StraightLineModel(EventModel):
    """
    Model parameters for a straight line model fit
    """
    intercept = models.FloatField(default=0, null=True, blank=True)
    intercept_error = models.FloatField(default=0, null=True, blank=True)
    gradient = models.FloatField(default=0, null=True, blank=True)
    gradient_error = models.FloatField(default=0, null=True, blank=True)

class VariableStar(models.Model):
    """
    Parameters of known variable stars
    """

    ra = models.FloatField(
        default=0,
        validators=[
           MinValueValidator(0.0),
           MaxValueValidator(360.0)
       ]
       )
    dec = models.FloatField(
        default=0,
        validators=[
           MinValueValidator(-90.0),
           MaxValueValidator(90.0)
       ]
       )
    ogle_id = models.CharField(max_length=30, null=True, blank=True)
    vvv_id = models.CharField(max_length=30, null=True, blank=True)
    gaia_id = models.CharField(max_length=30, null=True, blank=True)
    type = models.CharField(max_length=30, null=True, blank=True)

    def get_name(self):
        if self.ogle_id:
            return self.ogle_id
        elif self.gaia_id:
            return self.gaia_id
        elif self.vvv_id:
            return self.vvv_id
        else:
            return 'NoID'