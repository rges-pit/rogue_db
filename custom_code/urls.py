from django.urls import path, include

from .views import (
    RGESAlertListView, RGESAlertCreateView,
    EventModelListView, PSPLModelCreateView, FSPLModelCreateView, WideBoundPlanetModelCreateView,
    DavenportFlareModelCreateView, PitkinFlareModelCreateView,
    TargetCutfileView, EventListView,
)

candidates_urlpatterns = [
    path('', RGESAlertListView.as_view(), name='list'),
    path('create/', RGESAlertCreateView.as_view(), name='create'),
]

eventmodels_urlpatterns = [
    path('', EventModelListView.as_view(), name='list'),
    path('create/pspl/', PSPLModelCreateView.as_view(), name='create-pspl'),
    path('create/fspl/', FSPLModelCreateView.as_view(), name='create-fspl'),
    path('create/wideboundplanet/', WideBoundPlanetModelCreateView.as_view(), name='create-wide-bound-planet'),
    path('create/davenportflare/', DavenportFlareModelCreateView.as_view(), name='create-davenport-flare'),
    path('create/pitkinportflare/', PitkinFlareModelCreateView.as_view(), name='create-pitkin-flare'),
]

cutfiles_urlpatterns = [
    path('', TargetCutfileView.as_view(), name='list'),
]

events_urlpatterns = [
    path('', EventListView.as_view(), name='list'),
]

urlpatterns = [
    path('candidates/', include((candidates_urlpatterns, 'candidates'), namespace='candidates')),
    path('event-models/', include((eventmodels_urlpatterns, 'eventmodels'), namespace='eventmodels')),
    path('cutfiles/', include((cutfiles_urlpatterns, 'cutfiles'), namespace='cutfiles')),
    path('events/', include((events_urlpatterns, 'events'), namespace='events')),
]
