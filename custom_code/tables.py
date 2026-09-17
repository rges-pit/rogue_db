import django_tables2 as tables

from django.urls import reverse
from django.utils.html import format_html

from tom_common.htmx_table import HTMXTable
from .models import RGESAlert, EventModel, Event


class RGESAlertTable(HTMXTable):

    target = tables.Column(
        linkify=True,
        attrs={"a": {"hx-boost": "false"}}
    )
    alert_neural_network_confidence = tables.Column(verbose_name='Confidence (%)')

    class Meta(HTMXTable.Meta):
        model = RGESAlert
        fields = [
            'roman_id', 'target', 'alert_classification',
            'alert_neural_network_confidence', 'alert_delta_chi2', 'alert_timestamp',
            'alert_origin', 'ffp_candidate',
        ]
        # HTMXTable declares a 'selection' checkbox column for bulk actions; alerts
        # have no such grouping form, so it's excluded here.
        exclude = ['selection']

    partial_template_name = "custom_code/partials/alert_table_partial.html"


class EventModelTable(HTMXTable):
    """
    Lists EventModel rows including all model types.
    """

    # EventModel has no direct target field
    target = tables.Column(
        accessor='event__target',
        order_by='event__target',
        linkify=True,
        attrs={"a": {"hx-boost": "false"}}
    )

    class Meta(HTMXTable.Meta):
        model = EventModel
        fields = [
            'target', 'model_type', 'chisq', 'BIC'
        ]

        exclude = ['selection']

    partial_template_name = "custom_code/partials/eventmodel_table.html"

    def render_model_type(self, value, record):
        if not value:
            return value
        url = f"{reverse('eventmodels:parameters')}?model={record.pk}"
        return format_html(
            '<a href="#" hx-get="{}" hx-target="#model-parameters-container" '
            'hx-swap="innerHTML" hx-indicator="#model-parameters-progress">{}</a>',
            url, value,
        )

class EventRenderMixin:
    """
    Shared render_* methods for Event-based tables (EventTable, TargetEventTable).

    Deliberately NOT a Table subclass, and EventTable/TargetEventTable
    deliberately don't subclass each other -- django-tables2's
    DeclarativeColumnsMetaclass starts a subclass's base_columns as a full
    copy of the parent's base_columns, and Meta.fields on the subclass only
    ever adds/overrides columns, never removes them (only Meta.exclude does).
    So a smaller Meta.fields list on a Table subclass silently fails to
    narrow down an inherited column set -- confirmed by reading the
    metaclass source after TargetEventTable(EventTable) started leaking
    every column EventTable gained after it was first written. Two
    independent HTMXTable subclasses sharing this mixin avoids that trap
    entirely, regardless of how either Meta.fields list grows later.
    """

    def render_event_id(self, value, record):
        if not value:
            return value
        url = f"{reverse('eventmodels:list')}?event={record.pk}"
        return format_html(
            '<a href="#" hx-get="{}" hx-target="#event-models-container" '
            'hx-swap="innerHTML" hx-indicator="#event-models-progress">{}</a>',
            url, value,
        )

    def render_thumbnail(self, value):
        # value is the ImageFieldFile -- falsy when no file is set (older
        # Events predating this feature, or generation still pending/failed).
        # .url goes through the storage backend, so this works unchanged
        # whether files live on local disk or (later) S3.
        if not value:
            return ''
        return format_html('<img src="{}" alt="lightcurve thumbnail" style="max-height: 60px;">', value.url)


class EventTable(EventRenderMixin, HTMXTable):
    """
    Table to present information on lightcurve events, across every target.
    """

    target = tables.Column(linkify=True, attrs={"a": {"hx-boost": "false"}})

    class Meta(HTMXTable.Meta):
        model = Event
        fields = [
            'target', 'thumbnail', 'event_id', 'start_time', 'duration',
            'delta_chi2_PSPL', 'delta_BIC_PSPL',
            'delta_chi2_FSPL', 'delta_BIC_FSPL', 'delta_chi2_PSPL_bestflare',
            'delta_BIC_PSPL_bestflare', 'delta_chi2_FSPL_bestflare',
            'delta_BIC_FSPL_bestflare', 'DIA_centroid_shift', 'PSF_centroid_shift',
            'nearest_moving_object', 'period'
        ]
        # HTMXTable declares a 'selection' checkbox column for bulk actions; alerts
        # have no such grouping form, so it's excluded here.
        exclude = ['selection']

    partial_template_name = "custom_code/partials/event_table.html"

    def render_event_id(self, value, record):
        # Overrides EventRenderMixin.render_event_id: on the standalone Events
        # page, event_id -> EventDetailView
        if not value:
            return value
        url = reverse('events:detail', kwargs={'pk': record.pk})

        # It's necessary to set hx-boost="false" here to avoid clicks on the
        # event_id link being intercepted by AJAX and interpreted as a responsive table
        return format_html('<a href="{}" hx-boost="false">{}</a>', url, value)


class TargetEventTable(EventRenderMixin, HTMXTable):
    """
    Events table for the Events associated with a specific Target -- omits
    the target column EventTable has, since every row is already known to
    belong to the target whose page you're on.
    """

    # Not a model field -- empty_values=() makes django-tables2 always call
    # render_event_detail rather than treating a missing attribute as empty.
    event_detail = tables.Column(empty_values=(), verbose_name='', orderable=False)

    class Meta(HTMXTable.Meta):
        model = Event
        fields = [
            'event_id', 'event_detail', 'start_time', 'duration'
        ]
        exclude = ['selection']

    partial_template_name = "custom_code/partials/event_table.html"

    def render_event_detail(self, record):
        # event_id (via EventRenderMixin.render_event_id) still HTMX-swaps the
        # EventModel table on this tab -- this is a separate, plain link to
        # the full EventDetailView page, same hx-boost="false" reasoning as
        # EventTable.render_event_id.
        url = reverse('events:detail', kwargs={'pk': record.pk})
        return format_html('<a href="{}" hx-boost="false">Details</a>', url)
