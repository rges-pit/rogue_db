from custom_code.filters import EventFilterSet
from custom_code.models import Event
from custom_code.tables import EventTable

def event_tab_context(context):
    target = context['target']
    events_filter = EventFilterSet(context['request'].GET, queryset=Event.objects.filter(target=target))
    return {'filter': events_filter, 'table': EventTable(events_filter.qs)}