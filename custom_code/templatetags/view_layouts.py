from django import template
from custom_code.models import VariableStar

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