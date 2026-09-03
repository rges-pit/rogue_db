from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic.edit import CreateView
from tom_common.htmx_table import HTMXTableViewMixin
from django_filters.views import FilterView

from .models import RGESAlert, Event, EventModel, MicrolensingModel, FlareModel
from .filters import (
    RGESAlertFilterSet, EventModelFilterSet,
    MicrolensingCutfileFilterSet, FlareCutfileFilterSet,
    EventFilterSet
)
from .tables import RGESAlertTable, EventModelTable, EventTable
from .forms import RGESAlertForm, MicrolensingModelForm, FlareModelForm

class RGESAlertListView(LoginRequiredMixin, HTMXTableViewMixin, FilterView):
    """
    View for listing RGES alerts in the TOM. Requires the user to be logged in;
    anonymous users are redirected to login.
    """
    template_name = 'custom_code/rgesalerts_list.html'
    paginate_by = 20
    strict = False
    model = RGESAlert
    filterset_class = RGESAlertFilterSet
    table_class = RGESAlertTable

    ordering = ['-created_at']

    def get_context_data(self, *args, **kwargs):
        """
        Adds the number of alerts visible and the query string to the context object.

        :returns: context dictionary
        :rtype: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context['alert_count'] = context['record_count']
        context['query_string'] = self.request.META['QUERY_STRING']

        return context


class RGESAlertCreateView(LoginRequiredMixin, CreateView):
    """
    View for creating an RGESAlert. Requires the user to be logged in.
    """
    template_name = 'custom_code/rgesalert_form.html'
    model = RGESAlert
    form_class = RGESAlertForm

    def get_success_url(self):
        return reverse('candidates:list')

class EventListView(LoginRequiredMixin, HTMXTableViewMixin, FilterView):
    """
    View to list all Events associated with a Target.  Login required.
    """
    template_name = 'custom_code/events_list.html'
    paginate_by = 20
    strict = False
    model = Event
    filterset_class = EventFilterSet
    table_class = EventTable

    ordering = ['-created_at']

    def get_queryset(self, *args, **kwargs):
        queryset = super().get_queryset(*args, **kwargs)
        target_id = self.request.GET.get('target')
        if target_id:
            queryset = queryset.filter(target_id=target_id)
        return queryset

    def get_context_data(self, *args, **kwargs):
        """
        Adds the number of models visible and the query string to the context object.

        :returns: context dictionary
        :rtype: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context['event_count'] = context['record_count']
        context['query_string'] = self.request.META['QUERY_STRING']

        return context

class EventModelListView(LoginRequiredMixin, HTMXTableViewMixin, FilterView):
    """
    View for listing EventModels (of any type) in the TOM. Requires the user
    to be logged in; anonymous users are redirected to login.
    """
    template_name = 'custom_code/eventmodels_list.html'
    paginate_by = 20
    strict = False
    model = EventModel
    filterset_class = EventModelFilterSet
    table_class = EventModelTable

    ordering = ['-created_at']

    def get_context_data(self, *args, **kwargs):
        """
        Adds the number of models visible and the query string to the context object.

        :returns: context dictionary
        :rtype: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context['model_count'] = context['record_count']
        context['query_string'] = self.request.META['QUERY_STRING']

        return context


class MicrolensingModelCreateView(LoginRequiredMixin, CreateView):
    """
    View provides a form to enable a user to manually enter the parameters of
    a Microlensing model fit. Requires the user to be logged in.
    """
    template_name = 'custom_code/eventmodel_form.html'
    model = MicrolensingModel
    form_class = MicrolensingModelForm
    extra_context = {'model_type_label': 'Microlensing'}

    def get_success_url(self):
        return reverse('eventmodels:list')


class FlareModelCreateView(LoginRequiredMixin, CreateView):
    """
    View provides a form to enable a user to manually enter the parameters of
    a Flare model fit. Requires the user to be logged in.
    """
    template_name = 'custom_code/eventmodel_form.html'
    model = FlareModel
    form_class = FlareModelForm
    extra_context = {'model_type_label': 'Flare'}

    def get_success_url(self):
        return reverse('eventmodels:list')


class TargetCutfileView(HTMXTableViewMixin, FilterView):
    """
    This view enables a user to configure Microlensing- or Flare-model
    selection criteria based on min/max thresholds on that type's own
    parameters, and see the matching models displayed as a list. Which type
    is being searched is chosen via the `model_type` query parameter (see
    the tabs in target_cutfile_list.html) -- Microlensing and Flare models
    live in separate tables (see custom_code/models.py), so unlike the old
    single-table search, this can only ever query one type per request.
    """
    template_name = 'custom_code/target_cutfile_list.html'
    paginate_by = 20
    strict = False
    # Not model-type-dependent: both searches display results through the same
    # base-fields-only table (matching the pre-split behaviour, where the single
    # TargetModelTable only ever showed target/model_type here too). Set as a
    # plain attribute, not get_table_class(), because HTMXTableViewMixin's
    # get_template_names() reads self.table_class directly for HTMX requests.
    table_class = EventModelTable

    ordering = ['-created_at']

    def get_model_type(self):
        model_type = self.request.GET.get('model_type')
        return model_type if model_type in ('Microlensing', 'Flare') else 'Microlensing'

    def get_queryset(self, *args, **kwargs):
        # HTMXTableViewMixin.get_context_data() checks self.model.objects.exists(),
        # so self.model is set here (as well as being used below) rather than as a
        # class attribute, since which model applies depends on the request.
        self.model = FlareModel if self.get_model_type() == 'Flare' else MicrolensingModel
        return super().get_queryset(*args, **kwargs)

    def get_filterset_class(self):
        return FlareCutfileFilterSet if self.get_model_type() == 'Flare' else MicrolensingCutfileFilterSet

    def get_context_data(self, *args, **kwargs):
        """
        Adds the number of models visible, which model type is being searched,
        and the query string to the context object.

        :returns: context dictionary
        :rtype: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context['model_count'] = context['record_count']
        context['model_type'] = self.get_model_type()
        context['query_string'] = self.request.META['QUERY_STRING']

        return context
