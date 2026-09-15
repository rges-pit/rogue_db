from django import template

register = template.Library()

@register.inclusion_tag('custom_code/partials/source_banner.html')
def source_banner_data(target):
    """
    Function to render a banner with the target information
    """
    return {'target': target}