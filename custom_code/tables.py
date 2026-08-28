import django_tables2 as tables

from tom_common.htmx_table import HTMXTable
from .models import RGESAlert, TargetModel


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

class TargetModelTable(HTMXTable):

    target = tables.Column(
        linkify=True,
        attrs={"a": {"hx-boost": "false"}}
    )

    class Meta(HTMXTable.Meta):
        model = TargetModel
        fields = [
            'target', 'model_type',
        ]
        # HTMXTable declares a 'selection' checkbox column for bulk actions; alerts
        # have no such grouping form, so it's excluded here.
        exclude = ['selection']

    partial_template_name = "custom_code/partials/targetmodel_table_partial.html"
