import io

from tom_dataproducts.models import PhotometryReducedDatum
from custom_code.management.commands import data_utils
from custom_code.models import Event
from django.core.files.base import ContentFile
import numpy as np
import matplotlib.pyplot as plt

def generate_event_lightcurves(event):
    """
    Function to create a thumbnail image of the lightcurve segment of an
    event.  Since this is primarily aimed at Roman data the lightcurve we
    look for here is F146.
    """

    datasets = data_utils.get_reduced_data(event)

    # Lightcurve array columns: ts, brightness, brightness_error
    bandpass = 'F146'
    if bandpass in datasets.keys():
        lc = datasets[bandpass]

        # Select only the datapoints during the event
        event_end = event.start_time + event.duration
        idx = np.where((lc[:,0] >= event.start_time) & (lc[:,0] <= event_end))[0]

        # Plot lightcurve
        dt = 2460000.0
        fig, ax = plt.subplots(1,1, figsize=(6,4))
        ax.errorbar(
            lc[idx,0]-dt, lc[idx,1], yerr=lc[idx,2],
            marker='.', c='purple'
        )
        ax.set_xlabel('JD-' + str(dt) + ' [days]')
        ax.set_ylabel('Mag [' + bandpass + ']')
        ax.set_yinverted(True)

        # Render to an in-memory buffer rather than a literal path, so the
        # write goes through Event.thumbnail's storage backend (local disk
        # now, S3 later) instead of hardcoding a filesystem location.
        buf = io.BytesIO()
        fig.savefig(buf, format='png')
        plt.close(fig)

        filename = event.target.name + '_' + event.event_id + '_lc.png'
        # save=False: FieldFile.save() with save=True calls instance.save()
        # with no update_fields, which wouldn't satisfy on_event_saved's
        # update_fields guard and would spuriously re-trigger the moving-object
        # check. .update() persists the field without going through post_save.
        event.thumbnail.save(filename, ContentFile(buf.getvalue()), save=False)
        Event.objects.filter(pk=event.pk).update(thumbnail=event.thumbnail.name)
