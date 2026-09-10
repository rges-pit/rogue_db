from django.db.models import Q
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Row, Column, HTML

import django_filters

from tom_common.htmx_table import HTMXTableFilterSet

from .models import (RGESAlert, Event, EventModel, PSPLModel, FSPLModel,
                     DavenportFlareModel, PitkinFlareModel)
from .target_models import RogueTarget


class RGESAlertFilterSet(HTMXTableFilterSet):
    """
    Filters available for RGESAlert objects:
        - roman_id: Filter by the Roman Space Telescope alert identifier.
        - target: Filter by the associated Target.
        - alert_classification: Filter by the alert's classification.
        - query: General search across roman_id, classification, origin, and the
          associated target's name/aliases.
    """

    @property
    def form(self):
        """
        Override to show only the general search field. The base implementation
        auto-generates an "Advanced" panel from Meta.fields, but those fields
        aren't wired up for HTMX the way ``query`` is, so they don't do anything
        when changed. Rather than fix that plumbing, the panel is dropped here.
        """
        if not hasattr(self, '_form'):
            self._form = super().form
            self._form.helper.layout = Layout(
                Row(Column('query', css_class='form-group col-md-3')),
            )
        return self._form

    def general_search(self, queryset, name, value):
        """
        Search alerts by Roman ID, classification, origin, or the associated
        target's name/aliases.
        """
        if not value:
            return queryset

        q_set = (
            Q(roman_id__icontains=value)
            | Q(alert_classification__icontains=value)
            | Q(alert_origin__icontains=value)
            | Q(target__name__icontains=value)
            | Q(target__aliases__name__icontains=value)
        )
        return queryset.filter(q_set).distinct()

    class Meta:
        model = RGESAlert
        fields = ['roman_id', 'event', 'alert_classification']

class EventFilterSet(HTMXTableFilterSet):
    """
    Filters for Event objects relating to the given target
    """

    class Meta:
        model = Event
        fields = [
            'event_id', 'start_time', 'duration',
            'time_to_second_peak', 'second_peak_mag', 'coverage_fraction',
            'symmetry', 'Npoint_above_3sigma', 'delta_chi2_PSPL', 'delta_BIC_PSPL',
            'delta_chi2_FSPL', 'delta_BIC_FSPL',
            'delta_chi2_PSPL_bestflare', 'delta_BIC_PSPL_bestflare',
            'delta_chi2_FSPL_bestflare', 'delta_BIC_FSPL_bestflare', 'DIA_centroid_shift',
            'PSF_centroid_shift', 'Nlinked_events', 'nearest_moving_object',
            'angular_separation_moving_object', 'frac_below_baseline', 'max_excursion_below_baseline',
            'max_peak_periodogram', 'period'
        ]

class EventModelFilterSet(HTMXTableFilterSet):
    """
    Filters for EventModel objects -- this queries the shared base table, so it
    lists every model regardless of type (Microlensing, Flare, ...), but only
    ever sees base-class fields (event, model_type, chisq). Type-specific
    parameters (t0, peak_amplitude, etc.) live on the MicrolensingModel/
    FlareModel subclasses and aren't visible from this queryset -- see
    MicrolensingCutfileFilterSet/FlareCutfileFilterSet below for filtering those.
        - target: Filter by the associated Target (reached via event.target,
          since EventModel itself only has a Target indirectly through Event).
        - model_type: Filter by the model's type.
        - query: General search across target and model_type.
    """

    target = django_filters.ModelChoiceFilter(
        field_name='event__target',
        queryset=RogueTarget.objects.all(),
        label='Target',
    )

    @property
    def form(self):
        """
        Simplified version of the TOM Toolkit's HTMX search form.
        """
        if not hasattr(self, '_form'):
            self._form = super().form
            self._form.helper.layout = Layout(
                Row(Column('query', css_class='form-group col-md-3')),
            )
        return self._form

    def general_search(self, queryset, name, value):
        """
        General search of target_name and model_type
        """
        if not value:
            return queryset

        q_set = (
            Q(event__target__name__icontains=value)
            | Q(event__target__aliases__name__icontains=value)
            | Q(model_type__icontains=value)
        )
        return queryset.filter(q_set).distinct()

    class Meta:
        model = EventModel
        fields = ['model_type']


class PSPLCutfileFilterSet(HTMXTableFilterSet):
    """
    Filter to enable users to select a set of MicrolensingModels using min/max
    thresholds on the model's parameters (t0, u0, tE, rho, piEN, piEE), plus:
        - target: Filter by the associated Target (reached via event.target).
        - query: General search across the associated target's name/aliases.
    """

    target = django_filters.ModelChoiceFilter(
        field_name='event__target',
        queryset=RogueTarget.objects.all(),
        label='Target',
    )

    @property
    def form(self):
        """Override form property to configure crispy forms helper. This is to remove
        the Submit button which is not needed because HTMX is making AJAX requests.

        Also, add the FormHelper.Layout definition
        """
        if not hasattr(self, '_form'):
            self._form = super().form
            self._form.helper = FormHelper()
            self._form.helper.form_tag = False  # Don't render <form> tags (template handles it)
            self._form.helper.disable_csrf = True  # Template handles CSRF if needed
            self._form.helper.form_show_labels = True  # Explicitly clear any inputs/buttons

            self._form.helper.layout = Layout(
                Row(Column('query', css_class='form-group col-md-3')),
                Row(Column('target', css_class='col-md-6')),
                Div(
                    HTML('<h5>PSPL Microlensing Parameters</h5>'),
                    Row(
                        Column('t0_min', css_class='col-md-3'),
                        Column('t0_max', css_class='col-md-3'),
                        Column('u0_min', css_class='col-md-3'),
                        Column('u0_max', css_class='col-md-3'),
                        Column('tE_min', css_class='col-md-3'),
                        Column('tE_max', css_class='col-md-3'),
                    ),
                    Row(
                        Column('piEN_min', css_class='col-md-3'),
                        Column('piEN_max', css_class='col-md-3'),
                        Column('piEE_min', css_class='col-md-3'),
                        Column('piEE_max', css_class='col-md-3'),
                    ),
                    Row(
                        Column('chi2_min', css_class='col-md-3'),
                        Column('chi2_max', css_class='col-md-3'),
                        Column('BIC_min', css_class='col-md-3'),
                        Column('BIC_max', css_class='col-md-3'),
                    ),
                    HTML(
                        '<button type="submit" class="btn btn-primary mt-2">Search</button> '
                        '<button type="button" class="btn btn-secondary mt-2" onclick="saveCutfile()">Save</button>'
                    ),
                    css_class='border rounded p-3 mb-3',
                ),
            )
        return self._form

    t0_min = django_filters.NumberFilter(field_name='t0', lookup_expr='gte', label='t0 min')
    t0_max = django_filters.NumberFilter(field_name='t0', lookup_expr='lte', label='t0 max')
    u0_min = django_filters.NumberFilter(field_name='u0', lookup_expr='gte', label='u0 min')
    u0_max = django_filters.NumberFilter(field_name='u0', lookup_expr='lte', label='u0 max')
    tE_min = django_filters.NumberFilter(field_name='tE', lookup_expr='gte', label='tE min')
    tE_max = django_filters.NumberFilter(field_name='tE', lookup_expr='lte', label='tE max')
    piEN_min = django_filters.NumberFilter(field_name='piEN', lookup_expr='gte', label='piEN min')
    piEN_max = django_filters.NumberFilter(field_name='piEN', lookup_expr='lte', label='piEN max')
    piEE_min = django_filters.NumberFilter(field_name='piEE', lookup_expr='gte', label='piEE min')
    piEE_max = django_filters.NumberFilter(field_name='piEE', lookup_expr='lte', label='piEE max')
    chi2_min = django_filters.NumberFilter(field_name='chi2', lookup_expr='gte', label='chi2 min')
    chi2_max = django_filters.NumberFilter(field_name='chi2', lookup_expr='lte', label='chi2 max')
    BIC_min = django_filters.NumberFilter(field_name='bic', lookup_expr='gte', label='BIC min')
    BIC_max = django_filters.NumberFilter(field_name='bic', lookup_expr='lte', label='BIC max')

    def general_search(self, queryset, name, value):
        if not value:
            return queryset
        q_set = Q(event__target__name__icontains=value) | Q(event__target__aliases__name__icontains=value)
        return queryset.filter(q_set).distinct()

    class Meta:
        model = PSPLModel
        fields = []

class FSPLCutfileFilterSet(HTMXTableFilterSet):
    """
    Filter to enable users to select a set of MicrolensingModels using min/max
    thresholds on the model's parameters (t0, u0, tE, rho, piEN, piEE), plus:
        - target: Filter by the associated Target (reached via event.target).
        - query: General search across the associated target's name/aliases.
    """

    target = django_filters.ModelChoiceFilter(
        field_name='event__target',
        queryset=RogueTarget.objects.all(),
        label='Target',
    )

    @property
    def form(self):
        """Override form property to configure crispy forms helper. This is to remove
        the Submit button which is not needed because HTMX is making AJAX requests.

        Also, add the FormHelper.Layout definition
        """
        if not hasattr(self, '_form'):
            self._form = super().form
            self._form.helper = FormHelper()
            self._form.helper.form_tag = False  # Don't render <form> tags (template handles it)
            self._form.helper.disable_csrf = True  # Template handles CSRF if needed
            self._form.helper.form_show_labels = True  # Explicitly clear any inputs/buttons

            self._form.helper.layout = Layout(
                Row(Column('query', css_class='form-group col-md-3')),
                Row(Column('target', css_class='col-md-6')),
                Div(
                    HTML('<h5>FSPL Microlensing Parameters</h5>'),
                    Row(
                        Column('t0_min', css_class='col-md-3'),
                        Column('t0_max', css_class='col-md-3'),
                        Column('u0_min', css_class='col-md-3'),
                        Column('u0_max', css_class='col-md-3'),
                    ),
                    Row(
                        Column('tE_min', css_class='col-md-3'),
                        Column('tE_max', css_class='col-md-3'),
                        Column('rho_min', css_class='col-md-3'),
                        Column('rho_max', css_class='col-md-3'),
                    ),
                    Row(
                        Column('piEN_min', css_class='col-md-3'),
                        Column('piEN_max', css_class='col-md-3'),
                        Column('piEE_min', css_class='col-md-3'),
                        Column('piEE_max', css_class='col-md-3'),
                    ),
                    Row(
                        Column('chi2_min', css_class='col-md-3'),
                        Column('chi2_max', css_class='col-md-3'),
                        Column('BIC_min', css_class='col-md-3'),
                        Column('BIC_max', css_class='col-md-3'),
                    ),
                    HTML(
                        '<button type="submit" class="btn btn-primary mt-2">Search</button> '
                        '<button type="button" class="btn btn-secondary mt-2" onclick="saveCutfile()">Save</button>'
                    ),
                    css_class='border rounded p-3 mb-3',
                ),
            )
        return self._form

    t0_min = django_filters.NumberFilter(field_name='t0', lookup_expr='gte', label='t0 min')
    t0_max = django_filters.NumberFilter(field_name='t0', lookup_expr='lte', label='t0 max')
    u0_min = django_filters.NumberFilter(field_name='u0', lookup_expr='gte', label='u0 min')
    u0_max = django_filters.NumberFilter(field_name='u0', lookup_expr='lte', label='u0 max')
    tE_min = django_filters.NumberFilter(field_name='tE', lookup_expr='gte', label='tE min')
    tE_max = django_filters.NumberFilter(field_name='tE', lookup_expr='lte', label='tE max')
    rho_min = django_filters.NumberFilter(field_name='rho', lookup_expr='gte', label='rho min')
    rho_max = django_filters.NumberFilter(field_name='rho', lookup_expr='lte', label='rho max')
    piEN_min = django_filters.NumberFilter(field_name='piEN', lookup_expr='gte', label='piEN min')
    piEN_max = django_filters.NumberFilter(field_name='piEN', lookup_expr='lte', label='piEN max')
    piEE_min = django_filters.NumberFilter(field_name='piEE', lookup_expr='gte', label='piEE min')
    piEE_max = django_filters.NumberFilter(field_name='piEE', lookup_expr='lte', label='piEE max')
    chi2_min = django_filters.NumberFilter(field_name='chi2', lookup_expr='gte', label='chi2 min')
    chi2_max = django_filters.NumberFilter(field_name='chi2', lookup_expr='lte', label='chi2 max')
    BIC_min = django_filters.NumberFilter(field_name='bic', lookup_expr='gte', label='bic min')
    BIC_max = django_filters.NumberFilter(field_name='bic', lookup_expr='lte', label='bic max')

    def general_search(self, queryset, name, value):
        if not value:
            return queryset
        q_set = Q(event__target__name__icontains=value) | Q(event__target__aliases__name__icontains=value)
        return queryset.filter(q_set).distinct()

    class Meta:
        model = FSPLModel
        fields = []

class DavenportFlareCutfileFilterSet(HTMXTableFilterSet):
    """
    Filter to enable users to select a set of DavenportFlareModels using min/max
    thresholds on the model's parameters, plus:
        - target: Filter by the associated Target (reached via event.target).
        - query: General search across the associated target's name/aliases.
    """

    target = django_filters.ModelChoiceFilter(
        field_name='event__target',
        queryset=RogueTarget.objects.all(),
        label='Target',
    )

    @property
    def form(self):
        """Override form property to configure crispy forms helper. This is to remove
        the Submit button which is not needed because HTMX is making AJAX requests.

        Also, add the FormHelper.Layout definition
        """
        if not hasattr(self, '_form'):
            self._form = super().form
            self._form.helper = FormHelper()
            self._form.helper.form_tag = False
            self._form.helper.disable_csrf = True
            self._form.helper.form_show_labels = True

            self._form.helper.layout = Layout(
                Row(Column('query', css_class='form-group col-md-3')),
                Row(Column('target', css_class='col-md-6')),
                Div(
                    HTML('<h5>Davenport Flare Parameters</h5>'),
                    Row(
                        Column('t_peak_min', css_class='col-md-4'),
                        Column('t_peak_max', css_class='col-md-4'),
                    ),
                    Row(
                        Column('peak_amplitude_min', css_class='col-md-4'),
                        Column('peak_amplitude_max', css_class='col-md-4'),
                    ),
                    Row(
                        Column('t_FWHM_min', css_class='col-md-4'),
                        Column('t_FWHM_max', css_class='col-md-4'),
                    ),
                    Row(
                        Column('chi2_min', css_class='col-md-3'),
                        Column('chi2_max', css_class='col-md-3'),
                        Column('BIC_min', css_class='col-md-3'),
                        Column('BIC_max', css_class='col-md-3'),
                    ),
                    HTML(
                        '<button type="submit" class="btn btn-primary mt-2">Search</button> '
                        '<button type="button" class="btn btn-secondary mt-2" onclick="saveCutfile()">Save</button>'
                    ),
                    css_class='border rounded p-3 mb-3',
                ),
            )
        return self._form

    t_peak_min = django_filters.NumberFilter(
        field_name='t_peak', lookup_expr='gte', label='Time of peak min'
    )
    t_peak_max = django_filters.NumberFilter(
        field_name='t_peak', lookup_expr='lte', label='Time of peak max'
    )
    peak_amplitude_min = django_filters.NumberFilter(field_name='peak_amplitude', lookup_expr='gte', label='Peak amplitude min')
    peak_amplitude_max = django_filters.NumberFilter(field_name='peak_amplitude', lookup_expr='lte', label='Peak amplitude max')
    t_FWHM_min = django_filters.NumberFilter(
        field_name='t_FWHM', lookup_expr='gte', label='t_FWHM min'
    )
    t_FWHM_max = django_filters.NumberFilter(
        field_name='t_FWHM', lookup_expr='lte', label='t_FWHM max'
    )
    chi2_min = django_filters.NumberFilter(field_name='chi2', lookup_expr='gte', label='chi2 min')
    chi2_max = django_filters.NumberFilter(field_name='chi2', lookup_expr='lte', label='chi2 max')
    BIC_min = django_filters.NumberFilter(field_name='bic', lookup_expr='gte', label='bic min')
    BIC_max = django_filters.NumberFilter(field_name='bic', lookup_expr='lte', label='bic max')

    def general_search(self, queryset, name, value):
        if not value:
            return queryset
        q_set = Q(event__target__name__icontains=value) | Q(event__target__aliases__name__icontains=value)
        return queryset.filter(q_set).distinct()

    class Meta:
        model = DavenportFlareModel
        fields = []

class PitkinFlareCutfileFilterSet(HTMXTableFilterSet):
    """
    Filter to enable users to select a set of PitkinFlareModels using min/max
    thresholds on the model's parameters
    """

    target = django_filters.ModelChoiceFilter(
        field_name='event__target',
        queryset=RogueTarget.objects.all(),
        label='Target',
    )

    @property
    def form(self):
        """Override form property to configure crispy forms helper. This is to remove
        the Submit button which is not needed because HTMX is making AJAX requests.

        Also, add the FormHelper.Layout definition
        """
        if not hasattr(self, '_form'):
            self._form = super().form
            self._form.helper = FormHelper()
            self._form.helper.form_tag = False
            self._form.helper.disable_csrf = True
            self._form.helper.form_show_labels = True

            self._form.helper.layout = Layout(
                Row(Column('query', css_class='form-group col-md-3')),
                Row(Column('target', css_class='col-md-6')),
                Div(
                    HTML('<h5>Pitkin Flare Parameters</h5>'),
                    Row(
                        Column('t_peak_min', css_class='col-md-4'),
                        Column('t_peak_max', css_class='col-md-4'),
                    ),
                    Row(
                        Column('peak_amplitude_min', css_class='col-md-4'),
                        Column('peak_amplitude_max', css_class='col-md-4'),
                    ),
                    Row(
                        Column('tau_gaussian_rise_min', css_class='col-md-4'),
                        Column('tau_gaussian_rise_max', css_class='col-md-4'),
                    ),
                    Row(
                        Column('tau_exponential_decay_min', css_class='col-md-4'),
                        Column('tau_exponential_decay_max', css_class='col-md-4'),
                    ),
                    Row(
                        Column('chi2_min', css_class='col-md-3'),
                        Column('chi2_max', css_class='col-md-3'),
                        Column('BIC_min', css_class='col-md-3'),
                        Column('BIC_max', css_class='col-md-3'),
                    ),
                    HTML(
                        '<button type="submit" class="btn btn-primary mt-2">Search</button> '
                        '<button type="button" class="btn btn-secondary mt-2" onclick="saveCutfile()">Save</button>'
                    ),
                    css_class='border rounded p-3 mb-3',
                ),
            )
        return self._form

    t_peak_min = django_filters.NumberFilter(
        field_name='t_peak', lookup_expr='gte', label='Time of peak min'
    )
    t_peak_max = django_filters.NumberFilter(
        field_name='t_peak', lookup_expr='lte', label='Time of peak max'
    )
    peak_amplitude_min = django_filters.NumberFilter(field_name='peak_amplitude', lookup_expr='gte', label='Peak amplitude min')
    peak_amplitude_max = django_filters.NumberFilter(field_name='peak_amplitude', lookup_expr='lte', label='Peak amplitude max')
    tau_gaussian_rise_min = django_filters.NumberFilter(
        field_name='tau_gaussian_rise', lookup_expr='gte', label='tau_gaussian_rise min'
    )
    tau_gaussian_rise_max = django_filters.NumberFilter(
        field_name='tau_gaussian_rise', lookup_expr='lte', label='tau_gaussian_rise max'
    )
    tau_exponential_decay_min = django_filters.NumberFilter(
        field_name='tau_exponential_decay', lookup_expr='gte', label='tau_exponential_decay min'
    )
    tau_exponential_decay_max = django_filters.NumberFilter(
        field_name='tau_exponential_decay', lookup_expr='lte', label='tau_exponential_decay max'
    )
    chi2_min = django_filters.NumberFilter(field_name='chi2', lookup_expr='gte', label='chi2 min')
    chi2_max = django_filters.NumberFilter(field_name='chi2', lookup_expr='lte', label='chi2 max')
    BIC_min = django_filters.NumberFilter(field_name='bic', lookup_expr='gte', label='bic min')
    BIC_max = django_filters.NumberFilter(field_name='bic', lookup_expr='lte', label='bic max')

    def general_search(self, queryset, name, value):
        if not value:
            return queryset
        q_set = Q(event__target__name__icontains=value) | Q(event__target__aliases__name__icontains=value)
        return queryset.filter(q_set).distinct()

    class Meta:
        model = PitkinFlareModel
        fields = []