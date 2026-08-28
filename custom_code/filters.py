from django.db.models import Q
from crispy_forms.layout import Layout, Row, Column

from tom_common.htmx_table import HTMXTableFilterSet

from .models import RGESAlert, TargetModel


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
        fields = ['roman_id', 'target', 'alert_classification']

class TargetModelFilterSet(HTMXTableFilterSet):
    """
    Filters for TargetModel objects:
        - target: Filter by the associated Target.
        - model_type: Filter by the alert's classification.
        - query: General search across target and model_type.
    """

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
            Q(target__name__icontains=value)
            | Q(target__aliases__name__icontains=value)
            | Q(model_type__icontains=value)
        )
        return queryset.filter(q_set).distinct()

    class Meta:
        model = TargetModel
        fields = ['target', 'model_type']
