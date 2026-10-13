from django import template
from tom_dataproducts.models import PhotometryReducedDatum, ReducedDatum
from astropy.time import Time
from django.utils import timezone
from plotly import offline
import plotly.graph_objs as go
from plotly.subplots import make_subplots
import numpy as np
import datetime

import logging

logger = logging.getLogger(__name__)

register = template.Library()

# A plot with more points than this is drawn with WebGL. As SVG every point (and its error bar) is
# a separate element of the page, and a lightcurve of tens of thousands of points takes seconds to
# draw, and again for every zoom and pan.
WEBGL_MIN_POINTS = 5000

UNIX_EPOCH_JD = 2440587.5   # The Julian Date of 1970-01-01 00:00 UTC
JD_OFFSET = 2460000.0       # The plots show JD minus this

@register.inclusion_tag('tom_dataproducts/partials/photometry_mulens_model.html')
def photometry_mulens_model(mulens):
    """
    Renders a photometric plot for a target with a microlensing model.
    """

    # Plot the timeseries photometry data from all telescopes. P
    #
    # A target can have tens of thousands of points, so this is done in bulk.
    rows = list(PhotometryReducedDatum.objects.filter(target=mulens).order_by('source_name').values_list(
        'source_name', 'timestamp', 'brightness', 'brightness_error'
    ))

    datasets = {}
    if rows:
        sources = np.array([row[0] for row in rows])

        # UTC timestamps to JD - 2460000. A timestamp's Unix time is its UTC time of day, which is
        # what a JD of UTC counts too, so this is the JD astropy gives, to well within a second.
        jds = (
            np.array([row[1].timestamp() for row in rows]) / 86400.0
            + (UNIX_EPOCH_JD - JD_OFFSET)
        )
        # Limits and missing values come out as NaN, which the plot leaves out
        mags = np.array([row[2] for row in rows], dtype=float)
        errors = np.array([row[3] for row in rows], dtype=float)

        # Rounded to the precision of the data (a second, and a ten-thousandth of a magnitude),
        # as the rest of the digits only add to the size of what the browser is sent. The sources
        # are in the order of their names, for a legend that's the same each time.
        for source_name in dict.fromkeys(row[0] for row in rows):
            selected = sources == source_name
            datasets[source_name] = {
                'x': np.round(jds[selected], 5),
                'y': np.round(mags[selected], 4),
                'error': np.round(errors[selected], 4),
            }


    ### Try to plot models if available
    # Switched off since this will plot all models for all events
    # model_datums = ReducedDatum.objects.filter(target=mulens, data_type__icontains='lc_model')
    model_datums = ReducedDatum.objects.none()
    plot_code = plot_interactive_lightcurve(datasets, model_datums)

    return {
        'target': mulens,
        'plot': plot_code
    }

def calc_residuals(model_lc, dataset):
    """
    Function to calculate photometric residuals of a single dataset - model magnitudes.
    Does not assume both arrays have the same timestamps
    """

    model_mags = []
    for i in range(0, len(dataset['y']), 1):
        idx = np.where(model_lc[:, 0] == dataset['x'][i])[0]
        if len(idx) > 0:
            model_mags.append([dataset['x'][i], float((dataset['y'][i]-model_lc[idx,1])[0]), dataset['error'][i]])

    return np.array(model_mags)

def plot_interactive_lightcurve(
        datasets, model_datums,
        height=600, width=700,
        show_current_time=True,
        show_residuals=False,
        webgl=None
):
    """
    Function to produce an interactive lightcurve
    Lightcurves with less than 5000 points are plotted with Plotly but this is slow for
    larger datasets.  In this case, WegGL is used.
    """

    npoints = sum(len(dataset['x']) for dataset in datasets.values())
    if webgl is None:
        webgl = npoints > WEBGL_MIN_POINTS
    points_trace = go.Scattergl if webgl else go.Scatter

    # Layout with or without residuals
    plot_cols = 1
    plot_rows = 1
    if show_residuals:
        plot_rows = 2
        height *= 1.2

        fig = make_subplots(
            rows=plot_rows, cols=plot_cols,
            shared_xaxes=True,
            vertical_spacing=0.06,
            row_heights=[0.7, 0.3],
        )
    else:
        fig = make_subplots(
            rows=plot_rows, cols=plot_cols,
            shared_xaxes=True,
            vertical_spacing=0.06,
            row_heights=[1.0],
        )

    # Plot the main lightcurve
    for source_name, dataset in datasets.items():
        fig.add_trace(
            points_trace(
                x=dataset['x'], y=dataset['y'], mode='markers', name=source_name,
                error_y=dict(type='data', array=dataset['error'], visible=True),
            ),
            row=1, col=1,
        )

    # Optionally, plot residuals
    if show_residuals:
        for rd in model_datums:
            if 'PSPL' in rd.data_type:
                model_lc = np.zeros((len(rd.value['lc_model_time']),2))
                model_lc[:,0] = np.array(rd.value['lc_model_time']) - 2460000.0
                model_lc[:,1] = np.array(rd.value['lc_model_magnitude'])

                for source_name, dataset in datasets.items():
                    residuals = calc_residuals(model_lc, dataset)
                    fig.add_trace(
                        go.Scatter(
                            x=residuals[:,0], y=residuals[:,1], mode='markers', name='Data-PSPL',
                            error_y=dict(type='data', array=residuals[:,2], visible=True),
                        ),
                        row=2, col=1,
                    )

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
                xref='x',
                yref='paper',
                layer='below',
                line=dict(
                    color="Black",
                    width=1,
                    dash='dash',
                )
            ),
        )
    fig.update_xaxes(autorange=True)

    ### Try to plot model if exist
    if model_datums.count() > 0:
        for rd in model_datums:
            key_name = ''.join(rd.data_type.split('_')[-1])
            fig.add_trace(go.Scatter(x=np.array(rd.value['lc_model_time']) - 2460000,
                                 y=np.array(rd.value['lc_model_magnitude']),
                                 mode='lines',
                                 name=key_name,
                                 opacity=0.5,
                                 line=dict(width=5),
                                 ),
                        row=1, col=1,
                      )

    annotations = []
    if show_current_time:
        # Same autorange caveat as the shape above
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
        yaxis_title="Mag",
        legend=dict(            # Horizontal legend above the plot
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1,
        ),
        yaxis=dict(autorange='reversed'),
        xaxis=dict(autorange=True),
        height=height,
        width=width
    )
    if show_residuals:
        fig.update_yaxes(title_text="Residual", row=2, col=1)
        fig.update_xaxes(title_text="HJD-2460000", row=2, col=1)  # only the bottom axis needs a label
    else:
        fig.update_xaxes(title_text="HJD-2460000",  row=1, col=1)

    return offline.plot(fig, output_type='div', show_link=False, include_plotlyjs=False)

@register.inclusion_tag('tom_dataproducts/partials/photometry_mulens_model.html')
def photometry_event(event):
    """
    Generate an interactive plot using the lightcurve segment of a specific event
    """

    event_end = event.start_time + event.duration

    # Filter to the event's time window in the DB query, not by fetching the
    # target's entire photometry history (which can be tens of thousands of
    # points for a single target) and checking each row's JD in Python.
    start_dt = timezone.make_aware(Time(event.start_time, format='jd').datetime, datetime.timezone.utc)
    end_dt = timezone.make_aware(Time(event_end, format='jd').datetime, datetime.timezone.utc)
    qs = list(PhotometryReducedDatum.objects.filter(
        target=event.target, timestamp__gte=start_dt, timestamp__lte=end_dt
    ))

    datasets = {}
    if qs:
        jds = Time([rd.timestamp for rd in qs]).jd - 2460000.0
        for rd, jd in zip(qs, jds):
            if rd.source_name == 'Roman_F146':
                dataset = datasets.setdefault(rd.source_name, {'x': [], 'y': [], 'error': []})
                dataset['x'].append(jd)
                dataset['y'].append(rd.brightness)
                dataset['error'].append(rd.brightness_error)


    model_datums = ReducedDatum.objects.filter(
        target=event.target, data_type__icontains='lc_model_'+event.event_id
    )

    plot_code = plot_interactive_lightcurve(
        datasets, model_datums, height=400, width=500, show_current_time=False,
        show_residuals=True
    )

    return {
        'event': event,
        'plot': plot_code
    }
