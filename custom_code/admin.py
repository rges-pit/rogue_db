from django.contrib import admin
from .models import RGESAlert, MicrolensingModel, FlareModel, Event

@admin.register(RGESAlert)
class RGESAlertAdmin(admin.ModelAdmin):
    # Columns to show in the list view table
    list_display = ('roman_id', 'alert_classification', 'created_at')

    # Clickable filters on the right-hand sidebar
    list_filter = ('roman_id', 'alert_classification')

    # Search bar functionality at the top
    search_fields = ('roman_id', 'alert_classification')

@admin.register(Event)
class Event(admin.ModelAdmin):
    # Columns to show in the list view table
    list_display = ('target', 'event_id', 'window_start', 'window_end')

    # Clickable filters on the right-hand sidebar
    list_filter = ('target', 'event_id', 'window_start', 'window_end')

    # Search bar functionality at the top
    search_fields = ('target', 'event_id', 'window_start', 'window_end')

@admin.register(MicrolensingModel)
class MicrolensingModelAdmin(admin.ModelAdmin):
    # Columns to show in the list view table
    list_display = ('model_type', 'model_category')

    # Clickable filters on the right-hand sidebar
    list_filter = ('model_type', 'model_category')

    # Search bar functionality at the top
    search_fields = ('model_type', 'model_category')


@admin.register(FlareModel)
class FlareModelAdmin(admin.ModelAdmin):
    # Columns to show in the list view table
    list_display = ('model_type',)

    # Clickable filters on the right-hand sidebar
    list_filter = ('model_type',)

    # Search bar functionality at the top
    search_fields = ('model_type',)