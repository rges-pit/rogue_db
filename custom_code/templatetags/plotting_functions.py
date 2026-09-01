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
        height=600,
        width=700,

    )

    fig = go.Figure(data=plot_data, layout=layout)
    current_time = Time.now().jd - 2460000
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

    ### Try to plot model if exist
    qs2 = ReducedDatum.objects.filter(target=mulens, data_type='lc_model')
    if qs2.count() > 0:
        rd = qs2[0]
        fig.add_trace(go.Scatter(x=np.array(rd.value['lc_model_time']) - 2460000,
                                 y=np.array(rd.value['lc_model_magnitude']),
                                 mode='lines',
                                 name='Model',
                                 opacity=0.5,
                                 line=dict(color='rgb(227,227,227)',
                                           width=5, ),
                                 )
                      )

    fig.update_layout(

        annotations=[
            dict(
                x=current_time,
                xanchor="left",
                y=0.05,
                yref="paper",
                text="JD now : " + str(np.round(current_time, 3)) + " (" + str(Time.now().value).split(' ')[0] + ")",
                showarrow=False,
                textangle=-90, )
        ],
        xaxis_title="HJD-2460000",
        yaxis_title="Mag",
    )

    return {
        'target': mulens,
        'plot': offline.plot(fig, output_type='div', show_link=False)
    }
