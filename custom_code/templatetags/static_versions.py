import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def versioned_static(path):
    """
    The URL of a static file with the time it was last changed on the end of it, so that the URL changes
    when the file does. A browser can keep using a static file it has loaded for some time (the URL of one
    doesn't change, and nothing tells the browser that the file has), so that a fix to a script could
    go on not working for whoever had the old one. A file that can't be found has no version.
    """
    found = finders.find(path)
    if not found or isinstance(found, (list, tuple)):
        return static(path)
    return '%s?v=%d' % (static(path), os.path.getmtime(found))
