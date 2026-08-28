from django.urls import path, include

from .views import (
    RGESAlertListView, RGESAlertCreateView,
    TargetModelListView, TargetModelCreateView,
)

candidates_urlpatterns = [
    path('', RGESAlertListView.as_view(), name='list'),
    path('create/', RGESAlertCreateView.as_view(), name='create'),
]

targetmodels_urlpatterns = [
    path('', TargetModelListView.as_view(), name='list'),
    path('create/', TargetModelCreateView.as_view(), name='create'),
]

urlpatterns = [
    path('candidates/', include((candidates_urlpatterns, 'candidates'), namespace='candidates')),
    path('target-models/', include((targetmodels_urlpatterns, 'targetmodels'), namespace='targetmodels')),
]
