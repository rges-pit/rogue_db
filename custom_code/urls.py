from django.urls import path

from .views import RGESAlertListView, RGESAlertCreateView

app_name = 'alerts'

urlpatterns = [
    path('', RGESAlertListView.as_view(), name='list'),
    path('create/', RGESAlertCreateView.as_view(), name='create'),
]
