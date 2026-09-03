from django.apps import AppConfig
from django.urls import path, include


class CustomCodeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'custom_code'

    def include_url_paths(self):
        """
        Integration point for adding URL patterns to the TOM's URL configuration.
        """
        return [
            path('', include('custom_code.urls'))
        ]

    def nav_items(self):
        """
        Integration point for adding items to the navbar.
        """
        return [
            {'partial': 'custom_code/partials/navbar_item.html'},
            {'partial': 'custom_code/partials/navbar_item_eventmodels.html'},
            {'partial': 'custom_code/partials/navbar_item_cutfiles.html'},
        ]

    def target_detail_tabs(self):
        return [
            {'partial': 'custom_code/partials/target_events_tab.html',
             'context': 'custom_code.target_tabs.event_tab_context',
             'label': 'Events'}
        ]