from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic.edit import CreateView
from tom_common.htmx_table import HTMXTableViewMixin
from django_filters.views import FilterView

from .models import RGESAlert, TargetModel
from .filters import RGESAlertFilterSet, TargetModelFilterSet
from .tables import RGESAlertTable, TargetModelTable
from .forms import RGESAlertForm, TargetModelForm

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

class TargetModelListView(LoginRequiredMixin, HTMXTableViewMixin, FilterView):
    """
    View for listing TargetModels in the TOM. Requires the user to be logged in;
    anonymous users are redirected to login.
    """
    template_name = 'custom_code/targetmodels_list.html'
    paginate_by = 20
    strict = False
    model = TargetModel
    filterset_class = TargetModelFilterSet
    table_class = TargetModelTable

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


class TargetModelCreateView(LoginRequiredMixin, CreateView):
    """
    View for creating a TargetModel. Requires the user to be logged in.
    """
    template_name = 'custom_code/targetmodel_form.html'
    model = TargetModel
    form_class = TargetModelForm

    def get_success_url(self):
        return reverse('targetmodels:list')
