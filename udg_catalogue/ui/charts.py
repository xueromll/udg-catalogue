"""The catalogue charts in the slate system: the restyled 3D map and the analytics as Plotly figures.

``maps.py`` and ``analytics.py`` keep producing the report figures ``main.py``
writes; the dashboard restyles the map it gets from ``maps.py`` and draws the
analytics itself so one chart library and one type scale cover the whole app.
Chrome follows the slate tokens; data colours follow ``tokens.CATEGORICAL``
for identity and ``tokens.SEQUENTIAL`` for measures, so groups stay apart and
a measure reads at a glance.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from udg_catalogue.config import KEY_COLUMN
from udg_catalogue.maps import cluster_label
from udg_catalogue.ui.tokens import ACCENT, CANVAS, CATEGORICAL, FONT_MONO, INK, MUTED, SEPARATOR, TYPE_12, measure_scale, plotly_layout

MASS_COLUMN = "stellar_mass_solar"
RADIUS_COLUMN = "effective_radius_kpc"
COMPLETENESS_COLUMN = "completeness_pct"
MASS_LABEL = "stellar mass [M☉]"
RADIUS_LABEL = "R_eff [kpc]"
UNCLUSTERED = cluster_label(-1)
HISTOGRAM_BINS = 30
CHART_HEIGHT = 360
SCATTER_HEIGHT = 460
WALL = "#EDEFF2"
OTHER = "#C4CAD3"  # clusters beyond the palette: lighter than the unclustered grey, named on hover only
NO_VALUE = "no value"
_POINT_FIELDS = ("x", "y", "z", "text", "hovertext", "ids", "customdata")
AXIS: dict[str, Any] = {
    "gridcolor": SEPARATOR,
    "linecolor": INK,
    "linewidth": 1,
    "showline": True,
    "zeroline": False,
    "ticks": "outside",
    "ticklen": 4,
    "tickcolor": INK,
    "tickfont": {"family": FONT_MONO, "size": TYPE_12, "color": INK},
    "automargin": True,
    "title": {"font": {"size": TYPE_12, "color": INK}, "standoff": 8},
    "exponentformat": "power",
}
SCENE_AXIS: dict[str, Any] = {
    "gridcolor": SEPARATOR,
    "zerolinecolor": SEPARATOR,
    "backgroundcolor": WALL,
    "showbackground": True,
    "linecolor": MUTED,
    "tickfont": {"family": FONT_MONO, "size": TYPE_12, "color": INK},
    "title": {"font": {"size": TYPE_12, "color": INK}},
}
COLORBAR: dict[str, Any] = {
    "thickness": 8,
    "outlinewidth": 0,
    "len": 0.8,
    "tickfont": {"family": FONT_MONO, "size": TYPE_12, "color": INK},
    "title": {"font": {"size": TYPE_12, "color": INK}, "side": "right"},
}


def slate(figure: go.Figure, height: int | None = None) -> go.Figure:
    """Apply the base layout, the measure colour scale and the mono ticks to any Plotly figure, and drop its title."""
    layout: dict[str, Any] = plotly_layout(coloraxis={"colorscale": measure_scale(), "colorbar": COLORBAR})
    if height is not None:
        layout["height"] = height
    figure.update_layout(layout)
    figure.update_xaxes(AXIS)
    figure.update_yaxes(AXIS)
    return figure


def split_missing(trace: go.Scatter3d) -> go.Scatter3d | None:
    """Move the points whose measure is missing out of ``trace`` into a grey ``no value`` trace, or ``None`` if none is.

    A missing measure must not be drawn as the lowest value of the scale: on a
    dark-matter fraction map most galaxies have no fraction at all.
    """
    colour = np.asarray(trace.marker.color, dtype=float)
    missing = np.isnan(colour)
    if not missing.any():
        return None
    payload = trace.to_plotly_json()
    payload.pop("type", None)
    grey = go.Scatter3d(payload)
    keep = ~missing
    for field in _POINT_FIELDS:
        values = getattr(trace, field)
        if values is not None:
            setattr(grey, field, np.asarray(values)[missing])
            setattr(trace, field, np.asarray(values)[keep])
    if trace.marker.size is not None and np.ndim(trace.marker.size) == 1:
        grey.marker.size = np.asarray(trace.marker.size)[missing]
        trace.marker.size = np.asarray(trace.marker.size)[keep]
    trace.marker.color = colour[keep]
    grey.marker.update(color=MUTED, coloraxis=None, colorscale=None, showscale=False)
    grey.update(name=NO_VALUE, legendgroup=NO_VALUE, showlegend=True)
    return grey


def restyle_map(figure: go.Figure) -> go.Figure:
    """The 3D map on the canvas ground: Viridis for a measure, with galaxies that lack it in grey; by cluster, one hue
    each for the six largest clusters, grey for the unclustered and a lighter grey, off the legend, for every smaller
    cluster (hover still names it)."""
    slate(figure)
    figure.update_layout(
        scene={"bgcolor": CANVAS, **{axis: dict(SCENE_AXIS) for axis in ("xaxis", "yaxis", "zaxis")}},
        legend={"itemsizing": "constant"},
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
    )
    discrete = [trace for trace in figure.data if isinstance(trace.marker.color, str)]
    for trace in list(figure.data):
        if trace not in discrete and (grey := split_missing(trace)) is not None:
            figure.add_trace(grey)
    for trace in figure.data:
        trace.marker.line = {"width": 0}
        trace.marker.opacity = 0.9
    ranked = sorted((trace for trace in discrete if trace.name != UNCLUSTERED), key=lambda trace: -(0 if trace.x is None else len(trace.x)))
    for rank, trace in enumerate(ranked):
        if rank < len(CATEGORICAL):
            trace.marker.color = CATEGORICAL[rank]
        else:
            trace.marker.color = OTHER
            trace.showlegend = False
    for trace in discrete:
        if trace.name == UNCLUSTERED:
            trace.marker.color = MUTED
    return figure


def positive_values(catalogue: pd.DataFrame, column: str) -> pd.Series:
    if column not in catalogue.columns:
        return pd.Series(dtype=float)
    values = pd.to_numeric(catalogue[column], errors="coerce")
    return values[values > 0].astype(float)


def log_histogram(values: pd.Series, x_label: str, bins: int = HISTOGRAM_BINS) -> go.Figure | None:
    """Counts in log-spaced bins as ink bars, with the median as the one accent rule; ``None`` without data."""
    if values.empty:
        return None
    data = values.to_numpy()
    edges = np.logspace(np.log10(data.min()), np.log10(data.max()), bins + 1)
    edges[0], edges[-1] = min(edges[0], data.min()), max(edges[-1], data.max())
    counts, _edges = np.histogram(data, bins=edges)
    centres = np.sqrt(edges[:-1] * edges[1:])
    median = float(values.median())
    figure = go.Figure(
        go.Bar(
            x=edges[:-1],
            y=counts,
            width=np.diff(edges),
            offset=0,
            customdata=centres,
            marker={"color": INK, "line": {"width": 0}},
            hovertemplate="%{customdata:.3g}: %{y}<extra></extra>",
            name="count",
        )
    )
    figure.add_vline(x=median, line={"color": ACCENT, "width": 1})
    figure.add_annotation(
        x=np.log10(median),
        y=1,
        yref="paper",
        yanchor="bottom",
        yshift=4,
        text=f"median {median:.3g}",
        showarrow=False,
        xanchor="left",
        xshift=4,
        font={"family": FONT_MONO, "size": TYPE_12, "color": ACCENT},
    )
    slate(figure, CHART_HEIGHT)
    figure.update_xaxes(type="log", dtick=1, title_text=x_label)
    figure.update_yaxes(title_text="count", rangemode="tozero")
    return figure


def stellar_mass_histogram(catalogue: pd.DataFrame) -> go.Figure | None:
    return log_histogram(positive_values(catalogue, MASS_COLUMN), MASS_LABEL)


def effective_radius_histogram(catalogue: pd.DataFrame) -> go.Figure | None:
    return log_histogram(positive_values(catalogue, RADIUS_COLUMN), RADIUS_LABEL)


def mass_radius_scatter(catalogue: pd.DataFrame) -> go.Figure | None:
    """Mass against radius on log axes, coloured by completeness on the measure scale; ``None`` without both measures."""
    if not {MASS_COLUMN, RADIUS_COLUMN, COMPLETENESS_COLUMN}.issubset(catalogue.columns):
        return None
    mass = pd.to_numeric(catalogue[MASS_COLUMN], errors="coerce")
    radius = pd.to_numeric(catalogue[RADIUS_COLUMN], errors="coerce")
    keep = (mass > 0) & (radius > 0)
    if not keep.any():
        return None
    names = catalogue[KEY_COLUMN].astype(str) if KEY_COLUMN in catalogue.columns else pd.Series("", index=catalogue.index)
    figure = go.Figure(
        go.Scatter(
            x=radius[keep],
            y=mass[keep],
            mode="markers",
            marker={
                "size": 7,
                "color": pd.to_numeric(catalogue.loc[keep, COMPLETENESS_COLUMN], errors="coerce"),
                "coloraxis": "coloraxis",
                "line": {"color": CANVAS, "width": 0.5},
                "opacity": 0.85,
            },
            text=names[keep],
            hovertemplate="<b>%{text}</b><br>R_eff %{x:.3g} kpc<br>mass %{y:.3g} M☉<extra></extra>",
            name="galaxies",
        )
    )
    slate(figure, SCATTER_HEIGHT)
    figure.update_layout(coloraxis_colorbar_title_text="completeness %")
    figure.update_xaxes(type="log", dtick=1, title_text=RADIUS_LABEL)
    figure.update_yaxes(type="log", dtick=1, title_text=MASS_LABEL)
    return figure
