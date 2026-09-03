from django.urls import path, include

from .views import (
    RGESAlertListView, RGESAlertCreateView,
    EventModelListView, MicrolensingModelCreateView, FlareModelCreateView,
    TargetCutfileView,
)

candidates_urlpatterns = [
    path('', RGESAlertListView.as_view(), name='list'),
    path('create/', RGESAlertCreateView.as_view(), name='create'),
]

targetmodels_urlpatterns = [
    path('', EventModelListView.as_view(), name='list'),
    path('create/microlensing/', MicrolensingModelCreateView.as_view(), name='create-microlensing'),
    path('create/flare/', FlareModelCreateView.as_view(), name='create-flare'),
]

cutfiles_urlpatterns = [
    path('', TargetCutfileView.as_view(), name='list'),
]

urlpatterns = [
    path('candidates/', include((candidates_urlpatterns, 'candidates'), namespace='candidates')),
    path('target-models/', include((targetmodels_urlpatterns, 'targetmodels'), namespace='targetmodels')),
    path('cutfiles/', include((cutfiles_urlpatterns, 'cutfiles'), namespace='cutfiles')),
]
