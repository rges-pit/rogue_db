from django.contrib import admin
from .models import (RGESAlert, Event,
                     PSPLModel, FSPLModel, DavenportFlareModel, PitkinFlareModel,
                     SkewNormalModel, StraightLineModel)

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
    list_display = ('target', 'event_id', 'start_time', 'duration')

    # Clickable filters on the right-hand sidebar
    list_filter = ('target', 'event_id', 'start_time', 'duration')

    # Search bar functionality at the top
    search_fields = ('target', 'event_id', 'start_time', 'duration')

@admin.register(PSPLModel)
class PSPLModelAdmin(admin.ModelAdmin):
    # Columns to show in the list view table
    list_display = ('model_type', 't0', 'u0', 'tE')

    # Clickable filters on the right-hand sidebar
    list_filter = ('model_type', 't0', 'u0', 'tE')

    # Search bar functionality at the top
    search_fields = ('model_type', 't0', 'u0', 'tE')

@admin.register(FSPLModel)
class FSPLModelAdmin(admin.ModelAdmin):
    # Columns to show in the list view table
    list_display = ('model_type', 't0', 'u0', 'tE', 'rho')

    # Clickable filters on the right-hand sidebar
    list_filter = ('model_type', 't0', 'u0', 'tE', 'rho')

    # Search bar functionality at the top
    search_fields = ('model_type', 't0', 'u0', 'tE', 'rho')

@admin.register(DavenportFlareModel)
class DavenportFlareModelAdmin(admin.ModelAdmin):
    # Columns to show in the list view table
    list_display = ('model_type', 't_peak', 'peak_amplitude', 't_FWHM')

    # Clickable filters on the right-hand sidebar
    list_filter = ('model_type', 't_peak', 'peak_amplitude', 't_FWHM')

    # Search bar functionality at the top
    search_fields = ('model_type', 't_peak', 'peak_amplitude', 't_FWHM')


@admin.register(PitkinFlareModel)
class PitkinFlareModelAdmin(admin.ModelAdmin):
    # Columns to show in the list view table
    list_display = ('model_type', 't_peak', 'peak_amplitude', 'tau_gaussian_rise', 'tau_exponential_decay')

    # Clickable filters on the right-hand sidebar
    list_filter = ('model_type', 't_peak', 'peak_amplitude', 'tau_gaussian_rise', 'tau_exponential_decay')

    # Search bar functionality at the top
    search_fields = ('model_type', 't_peak', 'peak_amplitude', 'tau_gaussian_rise', 'tau_exponential_decay')

@admin.register(SkewNormalModel)
class SkewNormalModelAdmin(admin.ModelAdmin):
    # Columns to show in the list view table
    list_display = ('model_type', 't_peak', 'peak_amplitude', 'omega', 'alpha')

    # Clickable filters on the right-hand sidebar
    list_filter = ('model_type', 't_peak', 'peak_amplitude', 'omega', 'alpha')

    # Search bar functionality at the top
    search_fields = ('model_type', 't_peak', 'peak_amplitude', 'omega', 'alpha')

@admin.register(StraightLineModel)
class StraightLineModelAdmin(admin.ModelAdmin):
    # Columns to show in the list view table
    list_display = ('model_type', 'intercept', 'gradient')

    # Clickable filters on the right-hand sidebar
    list_filter = ('model_type', 'intercept', 'gradient')

    # Search bar functionality at the top
    search_fields = ('model_type', 'intercept', 'gradient')