from guardian.mixins import PermissionListMixin
from rest_framework.viewsets import ModelViewSet
from rest_framework import status
from custom_code.serializers import RGESAlertSerializer

class RGESAlertViewSet(ModelViewSet, PermissionListMixin):
    """
    Viewset for RGESAlerts.  It supports only create.
    """

    serializer_class = RGESAlertSerializer

    def create(self, request, *args, **kwargs):

        response = super().create(request, *args, **kwargs)

        if response.status_code == status.HTTP_201_CREATED:
            response.data['message'] = 'Alert added successfully'
        return response