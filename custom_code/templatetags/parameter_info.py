from django import template
from django.utils.html import format_html

from custom_code.parameter_docs import describe

register = template.Library()


@register.simple_tag
def param_info(name, scope='event'):
    """
    A small "i" icon, to put beside the name of a parameter, which shows what the parameter is in a
    pop-up when it is clicked (or reached with the keyboard). The pop-up is a Bootstrap popover, opened by
    the script of the page (see event_detail.html), which handles icons loaded into it later too.

    name is that of the field, scope is 'event' (the default) for the parameters of an event and its
    diagnostics, or 'model' for the parameters of a model fit. A parameter that has no description
    (see parameter_docs) gets no icon.
    """
    documented = describe(scope, name)
    if documented is None:
        return ''
    title, text = documented
    return format_html(
        '<a class="param-info" role="button" tabindex="0" data-bs-toggle="popover" data-bs-trigger="focus" '
        'data-bs-placement="top" data-bs-title="{}" data-bs-content="{}" aria-label="About {}">i</a>',
        title, text, title,
    )
