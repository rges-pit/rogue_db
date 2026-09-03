import django_tables2 as tables

from tom_common.htmx_table import HTMXTable
from .models import RGESAlert, EventModel


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
    Lists EventModel rows -- since this queries the shared MTI base table, it
    shows every model regardless of type (Microlensing, Flare, ...), but only
    ever has access to base-class fields. Type-specific parameters aren't
    shown here; see the per-type cutfile search for those.
    """

    # EventModel has no direct target field -- the target is reached through
    # its Event (RogueTarget -> Event -> EventModel), so the column accessor
    # traverses that relation rather than a same-named model field.
    target = tables.Column(
        accessor='event__target',
        order_by='event__target',
        linkify=True,
        attrs={"a": {"hx-boost": "false"}}
    )

    class Meta(HTMXTable.Meta):
        model = EventModel
        fields = [
            'target', 'model_type'
        ]
        # HTMXTable declares a 'selection' checkbox column for bulk actions; alerts
        # have no such grouping form, so it's excluded here.
        exclude = ['selection']

    partial_template_name = "custom_code/partials/eventmodel_table_partial.html"
