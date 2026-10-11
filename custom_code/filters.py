from dataclasses import dataclass

from django import forms
from django.db import models
from django.db.models import OuterRef, Q, Subquery
from django.http import QueryDict
from crispy_forms.layout import Layout, Row, Column

import django_filters
from django_filters.constants import EMPTY_VALUES

from tom_common.htmx_table import HTMXTableFilterSet

from .models import RGESAlert, Event, EventModel, SourceDiagnostics
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

    def general_search(self, queryset, name, value):
        """
        Search every field of the Event for the value, as the base implementation does, plus the
        source's name and aliases.

        The base implementation can't be used as it is: it tries a text lookup on each of the
        model's fields except the forward relations, and so on the reverse ones too (an Event's
        models and alerts), which don't support text lookups and raise a FieldError.
        """
        if not value:
            return queryset

        q_set = Q(target__name__icontains=value) | Q(target__aliases__name__icontains=value)
        for field in Event._meta.get_fields():
            if field.concrete and not field.is_relation:
                q_set |= Q(**{f'{field.name}__icontains': value})
        return queryset.filter(q_set).distinct()

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
            'angular_separation_moving_object'
        ]

class EventModelFilterSet(HTMXTableFilterSet):
    """
    Filters for the shared base table of EventModel objects
        - target: Filter by the associated Target (reached via event.target).
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


@dataclass(frozen=True)
class CutfileParam:
    """One searchable parameter: a min/max pair ('number') or a contains-match ('text')."""
    name: str    # model field name
    label: str
    kind: str = 'number'


@dataclass(frozen=True)
class CutfileModelType:
    """One of the EventModel types selectable in the cutfile query form."""
    slug: str        # A value of the form's model_type field (and the type's filter-name prefix)
    label: str
    db_value: str    # The matching EventModel.model_type value
    accessor: str    # Lookup from EventModel to this type's subclass table
    params: tuple    # Parameters specific to this type


def _number(name, label):
    return CutfileParam(name, label)


def _text(name, label):
    return CutfileParam(name, label, kind='text')


# Source parameters
CUTFILE_SOURCE_PARAMS = (
    _number('ra', 'RA [deg]'),
    _number('dec', 'Dec [deg]'),
    _number('baseline_magnitude', 'Baseline mag'),
    _text('nearest_flare_star', 'Nearest flare star'),
    _number('angular_separation_flare_star', 'Flare star separation [deg]'),
    _text('nearest_variable_star', 'Nearest variable star'),
    _number('angular_separation_variable', 'Variable star separation [deg]'),
    _text('nearest_variable_type', 'Nearest variable type'),
    _number('max_peak_periodogram', 'Max peak periodogram'),
    _number('period', 'Period [d]'),
)

# The source parameters held in the SourceDiagnostics table rather than on the target.
# A target has a series of diagnostics, each made at some time; a cutfile uses the latest one
# before the date of the cutfile.
DIAGNOSTIC_FIELDS = {
    field.name for field in SourceDiagnostics._meta.concrete_fields
} - {'id', 'target', 'created_at', 'updated_at'}

# SourceDiagnostics, most recently created first
LATEST_FIRST = ('-created_at', '-pk')


def diagnostic_alias(field):
    """The name of the annotation holding the latest value of a SourceDiagnostics field"""
    return f'latest_{field}'


def latest_diagnostic(field, as_of=None):
    """
    A subquery for the value of a SourceDiagnostics field in the most recently created entry
    for the target of the EventModel it's used on. Entries created after as_of, if given, are
    passed over: a cutfile finds what was known when it was made, so that running it again
    after the diagnostics have been revised gives the same models. NULL if the target has no
    such entry.
    """
    entries = SourceDiagnostics.objects.filter(target=OuterRef('event__target'))
    if as_of is not None:
        entries = entries.filter(created_at__lte=as_of)
    return Subquery(entries.order_by(*LATEST_FIRST).values(field)[:1])


def latest_diagnostics_by_target(target_ids, as_of=None):
    """The most recently created SourceDiagnostics (up to as_of, if given) of each target, by target ID"""
    entries = SourceDiagnostics.objects.filter(target__in=target_ids)
    if as_of is not None:
        entries = entries.filter(created_at__lte=as_of)
    latest = {}
    for entry in entries.order_by(*LATEST_FIRST):
        latest.setdefault(entry.target_id, entry)
    return latest


# Event parameters, excluding the target and thumbnail image attribute
_EVENT_EXCLUDED_FIELDS = {'id', 'target', 'thumbnail'}
_EVENT_PARAM_LABELS = {
    'event_id': 'Event ID',
    'start_time': 'Start time [JD]',
    'duration': 'Duration [d]',
    'peak_mag': 'Peak mag',
    'time_to_second_peak': 'Time to 2nd peak [d]',
    'second_peak_mag': '2nd peak mag',
    'coverage_fraction': 'Coverage fraction',
    'symmetry': 'Symmetry',
    'Npoint_above_3sigma': 'N points > 3σ',
    'delta_chi2_PSPL': 'Δχ² PSPL',
    'delta_BIC_PSPL': 'ΔBIC PSPL',
    'delta_chi2_FSPL': 'Δχ² FSPL',
    'delta_BIC_FSPL': 'ΔBIC FSPL',
    'delta_chi2_PSPL_bestflare': 'Δχ² PSPL best flare',
    'delta_BIC_PSPL_bestflare': 'ΔBIC PSPL best flare',
    'delta_chi2_FSPL_bestflare': 'Δχ² FSPL best flare',
    'delta_BIC_FSPL_bestflare': 'ΔBIC FSPL best flare',
    'DIA_centroid_shift': 'DIA centroid shift',
    'PSF_centroid_shift': 'PSF centroid shift',
    'Nlinked_events': 'N linked events',
    'nearest_moving_object': 'Nearest moving object',
    'angular_separation_moving_object': 'Moving object separation [arcsec]',
    'frac_below_baseline': 'Frac below baseline',
    'max_excursion_below_baseline': 'Max excursion below baseline',
}


def _event_params():
    params = []
    for field in Event._meta.get_fields():
        if not field.concrete or field.name in _EVENT_EXCLUDED_FIELDS:
            continue
        kind = 'text' if isinstance(field, models.CharField) else 'number'
        params.append(CutfileParam(field.name, _EVENT_PARAM_LABELS.get(field.name, field.name), kind))
    return tuple(params)


CUTFILE_EVENT_PARAMS = _event_params()

# EventModel parameters common to all model types
CUTFILE_MODEL_PARAMS = (
    _number('chisq', 'χ²'),
    _number('red_chisq', 'Reduced χ²'),
    _number('BIC', 'BIC'),
    _number('tau', 'MCMC autocorrelation time τ'),
    _number('tau_threshold', 'τ convergence threshold'),
    _text('fit_method', 'Fit method'),
)

CUTFILE_MODEL_TYPES = (
    CutfileModelType('pspl', 'PSPL microlensing', EventModel.ModelTypes.pspl, 'psplmodel', (
        _number('t0', 't0 [JD]'), _number('u0', 'u0'), _number('tE', 'tE [d]'),
        _number('piEN', 'piEN'), _number('piEE', 'piEE'), _number('A', 'Peak magnification A'),
    )),
    CutfileModelType('fspl', 'FSPL microlensing', EventModel.ModelTypes.fspl, 'fsplmodel', (
        _number('t0', 't0 [JD]'), _number('u0', 'u0'), _number('tE', 'tE [d]'), _number('rho', 'rho'),
        _number('piEN', 'piEN'), _number('piEE', 'piEE'), _number('A', 'Peak magnification A'),
    )),
    CutfileModelType('davenport_flare', 'Davenport flare', EventModel.ModelTypes.davenport_flare,
                     'davenportflaremodel', (
        _number('t_peak', 'Time of peak [JD]'), _number('peak_amplitude', 'Peak amplitude'),
        _number('t_FWHM', 't_FWHM [d]'),
    )),
    CutfileModelType('pitkin_flare', 'Pitkin flare', EventModel.ModelTypes.pitkin_flare,
                     'pitkinflaremodel', (
        _number('t_peak', 'Time of peak [JD]'), _number('peak_amplitude', 'Peak amplitude'),
        _number('tau_gaussian_rise', 'tau_gaussian_rise [d]'),
        _number('tau_exponential_decay', 'tau_exponential_decay [d]'),
    )),
    # Straight line and Baseline fits share a table (StraightLineModel), and so their
    # parameters; EventModel.model_type tells them apart, which each type here selects on.
    CutfileModelType('straight_line', 'Straight line', EventModel.ModelTypes.straightline,
                     'straightlinemodel', (
        _number('gradient', 'Gradient [mag/d]'), _number('intercept', 'Intercept at JD 0 [mag]'),
    )),
    CutfileModelType('baseline', 'Baseline', EventModel.ModelTypes.baseline,
                     'straightlinemodel', (
        _number('gradient', 'Gradient [mag/d]'), _number('intercept', 'Intercept at JD 0 [mag]'),
    )),
)
CUTFILE_MODEL_TYPES_BY_SLUG = {mt.slug: mt for mt in CUTFILE_MODEL_TYPES}

_INPUT_CLASS = 'form-control form-control-sm'


def _param_filters(group, lookup_prefix, params):
    """
    Build the filters for one group of parameters.
    """
    filters = {}
    for param in params:
        path = lookup_prefix + param.name

        # A source parameter held in SourceDiagnostics is filtered on an annotation of the latest
        # entry's value, which the filter set adds when the filter is used (it alone knows the
        # cutfile's moment). The filter is tagged with the field to annotate.
        diagnostic_field = param.name if group == 'source' and param.name in DIAGNOSTIC_FIELDS else None
        if diagnostic_field:
            path = diagnostic_alias(diagnostic_field)

        if param.kind == 'text':
            new = {f'{group}_{param.name}': django_filters.CharFilter(
                field_name=path, lookup_expr='icontains', label=param.label,
                widget=forms.TextInput(attrs={'class': _INPUT_CLASS, 'aria-label': param.label}),
            )}
        else:
            new = {}
            for bound, lookup_expr in (('min', 'gte'), ('max', 'lte')):
                new[f'{group}_{param.name}_{bound}'] = django_filters.NumberFilter(
                    field_name=path, lookup_expr=lookup_expr, label=f'{param.label} {bound}',
                    widget=forms.NumberInput(attrs={
                        'class': _INPUT_CLASS, 'step': 'any', 'placeholder': bound,
                        'aria-label': f'{param.label} {bound}',
                    }),
                )
        for filter_ in new.values():
            filter_.diagnostic_field = diagnostic_field
        filters.update(new)

    for filter_ in filters.values():
        filter_.cutfile_group = group
    return filters


def _build_cutfile_filters():
    filters = {}
    filters.update(_param_filters('source', 'event__target__', CUTFILE_SOURCE_PARAMS))
    filters.update(_param_filters('event', 'event__', CUTFILE_EVENT_PARAMS))
    filters.update(_param_filters('model', '', CUTFILE_MODEL_PARAMS))
    for model_type in CUTFILE_MODEL_TYPES:
        filters.update(_param_filters(model_type.slug, model_type.accessor + '__', model_type.params))
    return filters


class _CutfileFilterSetBase(HTMXTableFilterSet):
    """
    Selects EventModels of any of the types the form using all available diagnostic
    parameters.  Model-specific criteria only apply to models of that type.
    """

    query = django_filters.CharFilter(
        method='general_search', label='Target name',
        widget=forms.TextInput(attrs={
            'class': _INPUT_CLASS, 'placeholder': 'Name or alias contains...',
            'aria-label': 'Target name or alias',
        }),
    )
    target = django_filters.ModelChoiceFilter(
        field_name='event__target',
        queryset=RogueTarget.objects.all(),
        label='Target',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    # Model type checkboxes
    model_type = django_filters.MultipleChoiceFilter(
        choices=[(mt.slug, mt.label) for mt in CUTFILE_MODEL_TYPES],
        method='filter_model_types', widget=forms.CheckboxSelectMultiple,
    )

    # In order to keep the results reproducible, only event models created up to this
    # moment should be included.
    as_of = django_filters.IsoDateTimeFilter(
        field_name='created_at', lookup_expr='lte', widget=forms.HiddenInput,
    )

    def __init__(self, data=None, *args, **kwargs):
        data = QueryDict(mutable=True) if data is None else data.copy()
        requested = set(data.getlist('model_type'))
        slugs = [mt.slug for mt in CUTFILE_MODEL_TYPES if mt.slug in requested]
        data.setlist('model_type', slugs or [mt.slug for mt in CUTFILE_MODEL_TYPES])
        super().__init__(data, *args, **kwargs)

    @property
    def selected_model_types(self):
        """The model types searched, in the order of CUTFILE_MODEL_TYPES."""
        slugs = self.data.getlist('model_type')
        return [mt for mt in CUTFILE_MODEL_TYPES if mt.slug in slugs]

    @property
    def cutoff(self):
        """The moment the search is limited to (a datetime), or None for no limit."""
        self.form.is_valid()
        return self.form.cleaned_data.get('as_of')

    def general_search(self, queryset, name, value):
        if not value:
            return queryset
        q_set = Q(event__target__name__icontains=value) | Q(event__target__aliases__name__icontains=value)
        return queryset.filter(q_set).distinct()

    def with_latest_diagnostic(self, queryset, filter_, value):
        """
        For a filter on a source diagnostic that has a value, annotates the queryset with the latest
        entry's value of it, up to the cutfile's moment, for the filter to apply to.
        """
        field = getattr(filter_, 'diagnostic_field', None)
        alias = field and diagnostic_alias(field)
        if field is None or value in EMPTY_VALUES or alias in queryset.query.annotations:
            return queryset
        return queryset.annotate(**{alias: latest_diagnostic(field, self.cutoff)})

    def filter_queryset(self, queryset):
        """
        Applies the filters that hold for every model, then restricts to the model types
        searched.
        """
        selected = [mt.slug for mt in self.selected_model_types]
        by_type = {slug: [] for slug in selected}
        for name, value in self.form.cleaned_data.items():
            if name == 'model_type':
                continue
            filter_ = self.filters[name]
            group = getattr(filter_, 'cutfile_group', None)
            if group not in CUTFILE_MODEL_TYPES_BY_SLUG:
                queryset = self.with_latest_diagnostic(queryset, filter_, value)
                queryset = filter_.filter(queryset, value)
            elif group in by_type:
                by_type[group].append((filter_, value))

        # If the user selects a model type but sets no thresholds, then
        # all models of that type should be included in the queryset.
        plain, filtered = [], Q()
        for slug in selected:
            model_type = CUTFILE_MODEL_TYPES_BY_SLUG[slug]
            if not by_type[slug]:
                plain.append(model_type.db_value)
                continue
            models = queryset.model._default_manager.filter(model_type=model_type.db_value)
            for filter_, value in by_type[slug]:
                models = filter_.filter(models, value)
            filtered |= Q(pk__in=models.values('pk'))
        return queryset.filter(Q(model_type__in=plain) | filtered)

    def _fields(self, group, params):
        """The bound form fields for a list of parameters, as the form template renders them."""
        form = self.form
        fields = []
        for param in params:
            base = f'{group}_{param.name}'
            if param.kind == 'text':
                bound = [form[base]]
                fields.append({'label': param.label, 'kind': 'single', 'field': bound[0]})
            else:
                bound = [form[base + '_min'], form[base + '_max']]
                fields.append({'label': param.label, 'kind': 'range', 'min': bound[0], 'max': bound[1]})
            fields[-1]['active'] = any(b.value() not in (None, '') for b in bound)
        return fields

    def layout(self):
        """
        The layout for the cutfile query form.
        The different sets of parameters are sectioned out into collapsible sets of
        fields to make a cleaner UI.
        """
        form = self.form
        selected = self.selected_model_types

        def leading(label, name):
            bound = form[name]
            return {'label': label, 'kind': 'single', 'field': bound,
                    'active': bound.value() not in (None, '')}

        source = {
            'id': 'source', 'title': 'Source parameters',
            'fields': [leading('Target name', 'query'), leading('Target', 'target')]
                      + self._fields('source', CUTFILE_SOURCE_PARAMS),
        }
        event = {'id': 'event', 'title': 'Event parameters',
                 'fields': self._fields('event', CUTFILE_EVENT_PARAMS)}
        model = {
            'id': 'model', 'title': 'Event model parameters',
            'model_types': [
                {'slug': mt.slug, 'label': mt.label, 'included': mt in selected,
                 'fields': self._fields(mt.slug, mt.params)}
                for mt in CUTFILE_MODEL_TYPES
            ],
            'common_fields': self._fields('model', CUTFILE_MODEL_PARAMS),
        }

        for section in (source, event):
            section['count'] = sum(f['active'] for f in section['fields'])
        model['count'] = (
            sum(f['active'] for f in model['common_fields'])
            + sum(f['active'] for mt in model['model_types'] if mt['included'] for f in mt['fields'])
        )
        sections = [source, event, model]
        for section in sections:
            section['open'] = section['count'] > 0
        if not any(section['open'] for section in sections):
            model['open'] = True

        return {'sections': sections, 'as_of_field': form['as_of'], 'selected_model_types': selected}

    class Meta:
        model = EventModel
        fields = []

CutfileFilterSet = type(_CutfileFilterSetBase)(
    'CutfileFilterSet', (_CutfileFilterSetBase,), _build_cutfile_filters()
)
