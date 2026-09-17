from django import template
from tom_dataproducts.models import PhotometryReducedDatum, ReducedDatum
from astropy.time import Time
from plotly import offline
import plotly.graph_objs as go
import numpy as np

import logging

logger = logging.getLogger(__name__)

register = template.Library()

@register.inclusion_tag('tom_dataproducts/partials/photometry_mulens_model.html')
def photometry_mulens_model(mulens):
    """
    Renders a photometric plot for a target with a microlensing model.
    """

    # Plot the timeseries photometry data from all telescopes. Points are
    # grouped by source into one Scatter trace per source, since Plotly's
    # error_y.array (and x/y) expects an array of values per trace, not a
    # single point per trace.
    qs = PhotometryReducedDatum.objects.filter(target=mulens)

    datasets = {}
    for rd in qs:
        dataset = datasets.setdefault(rd.source_name, {'x': [], 'y': [], 'error': []})
        dataset['x'].append(Time(rd.timestamp).jd - 2460000.0)
        dataset['y'].append(rd.brightness)
        dataset['error'].append(rd.brightness_error)


    ### Try to plot models if available
    # Switched off since this will plot all models for all events
    # model_datums = ReducedDatum.objects.filter(target=mulens, data_type__icontains='lc_model')
    model_datums = ReducedDatum.objects.none()
    plot_code = plot_interactive_lightcurve(datasets, model_datums)

    return {
        'target': mulens,
        'plot': plot_code
    }

def plot_interactive_lightcurve(datasets, model_datums, height=600, width=700, show_current_time=True):
    """
    Function to produce an interactive lightcurve
    """
    plot_data = [
        go.Scatter(
            x=dataset['x'],
            y=dataset['y'],
            mode='markers',
            name=source_name,
            error_y=dict(
                type='data',
                array=dataset['error'],
                visible=True
            )
        ) for source_name, dataset in datasets.items()]

    layout = go.Layout(
        yaxis=dict(autorange='reversed'),
        xaxis=dict(autorange=True),
        height=height,
        width=width,

    )

    fig = go.Figure(data=plot_data, layout=layout)
    current_time = Time.now().jd - 2460000
    if show_current_time:

        fig.add_shape(
            # Line Vertical
            dict(
                type="line",
                x0=current_time,
                y0=0,
                x1=current_time,
                y1=1,
                yref='paper',
                layer='below',
                line=dict(
                    color="Black",
                    width=1,
                    dash='dash',
                )

            ))
    fig.update_xaxes(autorange=True)

    ### Try to plot model if exist
    if model_datums.count() > 0:
        for rd in model_datums:
            fig.add_trace(go.Scatter(x=np.array(rd.value['lc_model_time']) - 2460000,
                                 y=np.array(rd.value['lc_model_magnitude']),
                                 mode='lines',
                                 name=rd.data_type,
                                 opacity=0.5,
                                 line=dict(color='rgb(227,227,227)',
                                           width=5, ),
                                 )
                      )

    annotations = []
    if show_current_time:
        # Same autorange caveat as the shape above: this annotation's x is in
        # data coordinates too, so it's skipped along with the line for the
        # zoomed-in event plot.
        annotations.append(dict(
            x=current_time,
            xanchor="left",
            y=0.05,
            yref="paper",
            text="JD now : " + str(np.round(current_time, 3)) + " (" + str(Time.now().value).split(' ')[0] + ")",
            showarrow=False,
            textangle=-90,
        ))

    fig.update_layout(
        annotations=annotations,
        xaxis_title="HJD-2460000",
        yaxis_title="Mag",
    )

    return offline.plot(fig, output_type='div', show_link=False)

@register.inclusion_tag('tom_dataproducts/partials/photometry_mulens_model.html')
def photometry_event(event):
    """
    Generate an interactive plot using the lightcurve segment of a specific event
    """

    # Select only datapoints during the event
    qs = PhotometryReducedDatum.objects.filter(target=event.target)

    event_end = event.start_time + event.duration

    datasets = {}
    for rd in qs:
        ts = Time(rd.timestamp).jd
        if ts >= event.start_time and ts <= event_end:
            dataset = datasets.setdefault(rd.source_name, {'x': [], 'y': [], 'error': []})
            dataset['x'].append(ts - 2460000.0)
            dataset['y'].append(rd.brightness)
            dataset['error'].append(rd.brightness_error)


    model_datums = ReducedDatum.objects.filter(
        target=event.target, data_type__icontains='lc_model_'+event.event_id
    )

    plot_code = plot_interactive_lightcurve(
        datasets, model_datums, height=400, width=500, show_current_time=False
    )

    return {
        'event': event,
        'plot': plot_code
    }