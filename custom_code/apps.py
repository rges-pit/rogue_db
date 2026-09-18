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
            {'partial': 'custom_code/partials/navbar_item_events.html'},
            {'partial': 'custom_code/partials/navbar_item_cutfiles.html'},
        ]

    def target_detail_tabs(self):
        return [
            {'partial': 'custom_code/partials/target_events_tab.html',
             'context': 'custom_code.target_tabs.event_tab_context',
             'label': 'Events'}
        ]

    def ready(self):
        import custom_code.signals  # noqa

        # Point TargetListView (tom_targets/views.py) at this project's own
        # TargetTable instead of tom_base's same-named tom_targets.tables.TargetTable.
        # table_class is a plain class attribute set in tom_base's view code, not
        # something exposed via a template override or an AppConfig integration
        # point (unlike nav_items/target_detail_tabs above), so reassigning it
        # here -- after all apps are loaded -- is the least invasive way to swap
        # it in without editing tom_base directly.
        from tom_targets.views import TargetListView
        from custom_code.tables import TargetTable
        TargetListView.table_class = TargetTable
        TargetListView.paginate_by = 8