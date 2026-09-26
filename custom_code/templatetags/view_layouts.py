from django import template
from custom_code.models import EventModel

register = template.Library()

@register.inclusion_tag('custom_code/partials/source_banner.html')
def source_banner_data(target):
    """
    Function to render a banner with the target information
    """
    flare_separation_arcsec = target.angular_separation_flare_star * 3600.0
    variable_separation_arcsec = target.angular_separation_variable * 3600.0
    return {
        'target': target,
        'flare_separation_arcsec': flare_separation_arcsec,
        'variable_separation_arcsec': variable_separation_arcsec
        }

@register.inclusion_tag('custom_code/partials/event_banner.html')
def event_banner_data(event):
    """
    Function to compile the data presented in the banner on the EventDetailPage
    """
    flare_separation_arcsec = event.target.angular_separation_flare_star * 3600.0
    variable_separation_arcsec = event.target.angular_separation_variable * 3600.0
    return {
        'event': event,
        'target': event.target,
        'flare_separation_arcsec': flare_separation_arcsec,
        'variable_separation_arcsec': variable_separation_arcsec
        }

@register.inclusion_tag('custom_code/partials/event_model_buttons.html')
def event_model_buttons(event):
    """
    Function to create a button for each EventModel for the given Event, plus
    an Alerts button that loads the event's RGESAlerts into the same panel.
    """
    models = EventModel.objects.filter(event=event)
    return {'models': models, 'event': event}
