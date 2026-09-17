from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic.base import TemplateView
from django.views.generic.edit import CreateView
from django.views.generic.detail import DetailView
from django.core.exceptions import PermissionDenied
from tom_common.htmx_table import HTMXTableViewMixin
from django_filters.views import FilterView

from .models import (RGESAlert, Event, EventModel, MODEL_TYPE_CLASSES,
                     PSPLModel, FSPLModel, WideBoundPlanetModel,
                     DavenportFlareModel, PitkinFlareModel)
from .filters import (
    RGESAlertFilterSet, EventModelFilterSet,
    PSPLCutfileFilterSet, FSPLCutfileFilterSet,
    DavenportFlareCutfileFilterSet, PitkinFlareCutfileFilterSet,
    EventFilterSet
)
from .tables import RGESAlertTable, EventModelTable, EventTable, TargetEventTable
from .forms import (RGESAlertForm, PSPLModelForm, FSPLModelForm, WideBoundPlanetModelForm,
                    DavenportFlareModelForm, PitkinFlareModelForm)

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
    View to list all Events, across every target. Requires the user to be
    logged in; anonymous users are redirected to login. See
    TargetEventListView for the version scoped to one target's Events tab.
    """
    template_name = 'custom_code/events_list.html'
    paginate_by = 20
    strict = False
    model = Event
    filterset_class = EventFilterSet
    table_class = EventTable

    # Event has no created_at/timestamp field (unlike EventModel/RGESAlert),
    # so -start_time (most recent event window first) is the closest
    # available equivalent to this app's usual "newest first" default.
    ordering = ['-start_time']

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

class EventDetailView(LoginRequiredMixin,DetailView):
    """
    View that handles the display of the target details.
    """
    template_name = 'custom_code/event_detail.html'
    model = Event

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        if not qs.exists() and Event.objects.filter(pk=self.kwargs.get("pk")).exists():
            raise PermissionDenied('You do not have permission to view this event')
        else:
            return qs

    def get_context_data(self, *args, **kwargs):
        """
        :returns: context object
        :rtype: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context['event'] = self.object
        context['target'] = self.object.target
        return context

class TargetEventListView(EventListView):
    """
    Events tab on TargetDetailView -- scopes EventListView to one target's
    Events (?target=<pk>, baked into the tab's hx-get URL by target_events_tab.html)
    and swaps in TargetEventTable, which drops the now-redundant target column.
    """
    table_class = TargetEventTable

    def get_queryset(self, *args, **kwargs):
        queryset = super().get_queryset(*args, **kwargs)
        target_id = self.request.GET.get('target')
        if target_id:
            queryset = queryset.filter(target_id=target_id)
        return queryset


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

    def get_queryset(self, *args, **kwargs):
        # Optional scoping to one Event's models -- used by the Events tab on
        # TargetDetailView (see EventTable.render_event_id), which links each
        # event_id to ?event=<pk> here. The standalone EventModel list page
        # doesn't set this param, so it still shows every model, unfiltered.
        queryset = super().get_queryset(*args, **kwargs)
        event_id = self.request.GET.get('event')
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        return queryset

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


class EventModelParametersView(LoginRequiredMixin, TemplateView):
    """
    Renders the type-specific fit parameters for one EventModel row (?model=<pk>).
    Requires the user to be logged in.
    """
    template_name = 'custom_code/partials/event_model_parameters.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base = get_object_or_404(EventModel, pk=self.request.GET.get('model'))
        model_class = MODEL_TYPE_CLASSES.get(base.model_type)

        parameters = []
        if model_class:
            instance = get_object_or_404(model_class, pk=base.pk)

            parameters = [
                (field.verbose_name, getattr(instance, field.attname))
                for field in type(instance)._meta.local_fields
                if not getattr(field.remote_field, 'parent_link', False)
            ]

        context['model_type'] = base.model_type
        context['parameters'] = parameters
        return context


class PSPLModelCreateView(LoginRequiredMixin, CreateView):
    """
    View provides a form to enable a user to manually enter the parameters of
    a Point-Source, Point-Lens microlensing model fit. Requires the user to be logged in.
    """
    template_name = 'custom_code/eventmodel_form.html'
    model = PSPLModel
    form_class = PSPLModelForm
    extra_context = {'model_type_label': 'PSPL'}

    def get_success_url(self):
        return reverse('eventmodels:list')

class FSPLModelCreateView(LoginRequiredMixin, CreateView):
    """
    View provides a form to enable a user to manually enter the parameters of
    a Finite-Source, Point-Lens microlensing model fit. Requires the user to be logged in.
    """
    template_name = 'custom_code/eventmodel_form.html'
    model = FSPLModel
    form_class = FSPLModelForm
    extra_context = {'model_type_label': 'FSPL'}

    def get_success_url(self):
        return reverse('eventmodels:list')

class WideBoundPlanetModelCreateView(LoginRequiredMixin, CreateView):
    """
    View provides a form to enable a user to manually enter the parameters of
    a wide-bound planet microlensing model fit. Requires the user to be logged in.
    """
    template_name = 'custom_code/eventmodel_form.html'
    model = WideBoundPlanetModel
    form_class = WideBoundPlanetModelForm
    extra_context = {'model_type_label': 'Wide bound planet'}

    def get_success_url(self):
        return reverse('eventmodels:list')

class DavenportFlareModelCreateView(LoginRequiredMixin, CreateView):
    """
    View provides a form to enable a user to manually enter the parameters of
    a Flare model fit. Requires the user to be logged in.
    """
    template_name = 'custom_code/eventmodel_form.html'
    model = DavenportFlareModel
    form_class = DavenportFlareModelForm
    extra_context = {'model_type_label': 'Flare'}

    def get_success_url(self):
        return reverse('eventmodels:list')


class PitkinFlareModelCreateView(LoginRequiredMixin, CreateView):
    """
    View provides a form to enable a user to manually enter the parameters of
    a Flare model fit. Requires the user to be logged in.
    """
    template_name = 'custom_code/eventmodel_form.html'
    model = PitkinFlareModel
    form_class = PitkinFlareModelForm
    extra_context = {'model_type_label': 'Flare'}

    def get_success_url(self):
        return reverse('eventmodels:list')

class TargetCutfileView(HTMXTableViewMixin, FilterView):
    """
    This view enables a user to configure microlensing or flare-model
    selection criteria based on min/max thresholds on that type's own
    parameters, and see the matching models displayed as a list.
    """
    template_name = 'custom_code/target_cutfile_list.html'
    paginate_by = 20
    strict = False
    table_class = EventModelTable

    ordering = ['-created_at']

    def get_model_type(self):
        # Values match the ?model_type= query params used by the tab links
        # in target_cutfile_list.html.
        model_set = ('pspl', 'fspl', 'davenport_flare', 'pitkin_flare')
        model_type = self.request.GET.get('model_type')
        return model_type if model_type in model_set else 'pspl'

    def get_queryset(self, *args, **kwargs):
        if self.get_model_type() == 'pspl':
            self.model = PSPLModel
        elif self.get_model_type() == 'fspl':
            self.model = FSPLModel
        elif self.get_model_type() == 'davenport_flare':
            self.model = DavenportFlareModel
        elif self.get_model_type() == 'pitkin_flare':
            self.model = PitkinFlareModel
        else:
            self.model = PSPLModel
        return super().get_queryset(*args, **kwargs)

    def get_filterset_class(self):
        if self.get_model_type() == 'pspl':
            filter_set = PSPLCutfileFilterSet
        elif self.get_model_type() == 'fspl':
            filter_set = FSPLCutfileFilterSet
        elif self.get_model_type() == 'davenport_flare':
            filter_set = DavenportFlareCutfileFilterSet
        elif self.get_model_type() == 'pitkin_flare':
            filter_set = PitkinFlareCutfileFilterSet
        else:
            filter_set = PSPLCutfileFilterSet
        return filter_set

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
