from django.db.models import Q
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Row, Column, HTML

import django_filters

from tom_common.htmx_table import HTMXTableFilterSet

from .models import RGESAlert, EventModel, MicrolensingModel, FlareModel
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


class MicrolensingCutfileFilterSet(HTMXTableFilterSet):
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
                    HTML('<h5>Microlensing Parameters</h5>'),
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

    def general_search(self, queryset, name, value):
        if not value:
            return queryset
        q_set = Q(event__target__name__icontains=value) | Q(event__target__aliases__name__icontains=value)
        return queryset.filter(q_set).distinct()

    class Meta:
        model = MicrolensingModel
        fields = []


class FlareCutfileFilterSet(HTMXTableFilterSet):
    """
    Filter to enable users to select a set of FlareModels using min/max
    thresholds on the model's parameters (peak_amplitude, rise_time, tau1,
    tau2, equivalent_duration), plus:
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
                    HTML('<h5>Flare Parameters</h5>'),
                    Row(
                        Column('peak_amplitude_min', css_class='col-md-4'),
                        Column('peak_amplitude_max', css_class='col-md-4'),
                    ),
                    Row(
                        Column('rise_time_min', css_class='col-md-4'),
                        Column('rise_time_max', css_class='col-md-4'),
                    ),
                    Row(
                        Column('equivalent_duration_min', css_class='col-md-4'),
                        Column('equivalent_duration_max', css_class='col-md-4'),
                    ),
                    Row(
                        Column('tau1_min', css_class='col-md-4'),
                        Column('tau1_max', css_class='col-md-4'),
                        Column('tau2_min', css_class='col-md-4'),
                        Column('tau2_max', css_class='col-md-4'),
                    ),
                    HTML(
                        '<button type="submit" class="btn btn-primary mt-2">Search</button> '
                        '<button type="button" class="btn btn-secondary mt-2" onclick="saveCutfile()">Save</button>'
                    ),
                    css_class='border rounded p-3 mb-3',
                ),
            )
        return self._form

    peak_amplitude_min = django_filters.NumberFilter(
        field_name='peak_amplitude', lookup_expr='gte', label='Peak amplitude min'
    )
    peak_amplitude_max = django_filters.NumberFilter(
        field_name='peak_amplitude', lookup_expr='lte', label='Peak amplitude max'
    )
    rise_time_min = django_filters.NumberFilter(field_name='rise_time', lookup_expr='gte', label='Rise time min')
    rise_time_max = django_filters.NumberFilter(field_name='rise_time', lookup_expr='lte', label='Rise time max')
    equivalent_duration_min = django_filters.NumberFilter(
        field_name='equivalent_duration', lookup_expr='gte', label='Equivalent duration min'
    )
    equivalent_duration_max = django_filters.NumberFilter(
        field_name='equivalent_duration', lookup_expr='lte', label='Equivalent duration max'
    )
    tau1_min = django_filters.NumberFilter(field_name='tau1', lookup_expr='gte', label='tau1 min')
    tau1_max = django_filters.NumberFilter(field_name='tau1', lookup_expr='lte', label='tau1 max')
    tau2_min = django_filters.NumberFilter(field_name='tau2', lookup_expr='gte', label='tau2 min')
    tau2_max = django_filters.NumberFilter(field_name='tau2', lookup_expr='lte', label='tau2 max')

    def general_search(self, queryset, name, value):
        if not value:
            return queryset
        q_set = Q(event__target__name__icontains=value) | Q(event__target__aliases__name__icontains=value)
        return queryset.filter(q_set).distinct()

    class Meta:
        model = FlareModel
        fields = []
