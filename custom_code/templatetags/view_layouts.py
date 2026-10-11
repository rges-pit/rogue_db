from django import template
from custom_code.models import EventModel, SourceDiagnostics

register = template.Library()

def fetch_latest_source_diagnostics(target):
    """
    Function to retrieve the latest entry in the Source Diagnostics table
    for this target
    """
    qs = SourceDiagnostics.objects.filter(target=target).order_by('-created_at')
    if qs.count() > 0:
        sdiagnostics = qs[0]
        flare_separation_arcsec = sdiagnostics.angular_separation_flare_star * 3600.0
        variable_separation_arcsec = sdiagnostics.angular_separation_variable * 3600.0
        return {
            'target': target,
            'classification': sdiagnostics.classification,
            'baseline_magnitude': sdiagnostics.baseline_magnitude,
            'baseline_mag_error': sdiagnostics.baseline_mag_error,
            'baseline_mag_passband': sdiagnostics.baseline_mag_passband,
            'nearest_flare_star': sdiagnostics.nearest_flare_star,
            'flare_separation_arcsec': flare_separation_arcsec,
            'nearest_variable_star': sdiagnostics.nearest_variable_star,
            'nearest_variable_type': sdiagnostics.nearest_variable_type,
            'variable_separation_arcsec': variable_separation_arcsec,
            'max_peak_periodogram': sdiagnostics.max_peak_periodogram,
            'period': sdiagnostics.period
        }
    else:
        return {
            'target': target,
            'classification': None,
            'baseline_magnitude': 0.0,
            'baseline_mag_error': 0.0,
            'baseline_mag_passband': '',
            'nearest_flare_star': '',
            'flare_separation_arcsec': 0.0,
            'nearest_variable_star': '',
            'nearest_variable_type': '',
            'variable_separation_arcsec': 0.0,
            'max_peak_periodogram': None,
            'period': None
        }
@register.inclusion_tag('custom_code/partials/source_banner.html')
def source_banner_data(target):
    """
    Function to render a banner with the target information
    """
    response = fetch_latest_source_diagnostics(target)
    return response

@register.inclusion_tag('custom_code/partials/event_banner.html')
def event_banner_data(event):
    """
    Function to compile the data presented in the banner on the EventDetailPage
    """
    response = fetch_latest_source_diagnostics(event.target)
    response['event'] = event
    return response

@register.inclusion_tag('custom_code/partials/event_model_buttons.html')
def event_model_buttons(event):
    """
    Function to create a button for each EventModel for the given Event, plus
    an Alerts button that loads the event's RGESAlerts into the same panel.
    """
    models = EventModel.objects.filter(event=event)
    return {'models': models, 'event': event}
