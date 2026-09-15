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

class EventTable(HTMXTable):
    """
    Table to present information on lightcurve events
    """

    class Meta(HTMXTable.Meta):
        model = Event
        fields = [
            'event_id', 'start_time', 'duration'
        ]
        # HTMXTable declares a 'selection' checkbox column for bulk actions; alerts
        # have no such grouping form, so it's excluded here.
        exclude = ['selection']

    partial_template_name = "custom_code/partials/event_table.html"

    def render_event_id(self, value, record):
        # Clicking an event_id loads that Event's EventModels into the
        # #event-models-container placeholder below the table (see
        # target_events_tab.html) rather than navigating away.
        if not value:
            return value
        url = f"{reverse('eventmodels:list')}?event={record.pk}"
        return format_html(
            '<a href="#" hx-get="{}" hx-target="#event-models-container" '
            'hx-swap="innerHTML" hx-indicator="#event-models-progress">{}</a>',
            url, value,
        )
