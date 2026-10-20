"""The catalogue charts in the slate system: the restyled 3D map and the analytics as single-hue Plotly figures.

``maps.py`` and ``analytics.py`` keep producing the report figures ``main.py``
writes; the dashboard restyles the map it gets from ``maps.py`` and draws the
analytics itself so one chart library, one palette and one type scale cover the
whole app.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from udg_catalogue.config import KEY_COLUMN
from udg_catalogue.maps import cluster_label
from udg_catalogue.ui.tokens import ACCENT, CANVAS, COMMUNITY_RAMP, FONT_MONO, INK, MUTED, SEPARATOR, TYPE_12, ink_scale, plotly_layout

MASS_COLUMN = "stellar_mass_solar"
RADIUS_COLUMN = "effective_radius_kpc"
COMPLETENESS_COLUMN = "completeness_pct"
MASS_LABEL = "stellar mass [M☉]"
RADIUS_LABEL = "R_eff [kpc]"
UNCLUSTERED = cluster_label(-1)
HISTOGRAM_BINS = 30
CHART_HEIGHT = 360
AXIS: dict[str, Any] = {
    "gridcolor": SEPARATOR,
    "linecolor": INK,
    "linewidth": 1,
    "zeroline": False,
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
    """Apply the base layout, the ink colour scale and the mono ticks to any Plotly figure, and drop its title."""
    layout: dict[str, Any] = plotly_layout(coloraxis={"colorscale": ink_scale(), "colorbar": COLORBAR})
    if height is not None:
        layout["height"] = height
    figure.update_layout(layout)
    figure.update_xaxes(AXIS)
    figure.update_yaxes(AXIS)
    return figure


def restyle_map(figure: go.Figure) -> go.Figure:
    """The 3D map on the canvas ground: a single-hue scale for a measure, ramp steps per cluster, grey for the unclustered."""
    slate(figure)
    figure.update_layout(
        scene={
            axis: {"gridcolor": SEPARATOR, "backgroundcolor": CANVAS, "zerolinecolor": SEPARATOR, "showbackground": True}
            for axis in ("xaxis", "yaxis", "zaxis")
        },
        legend={"itemsizing": "constant"},
    )
    step = 0
    for trace in figure.data:
        if not isinstance(trace.marker.color, str):
            continue
        if trace.name == UNCLUSTERED:
            trace.marker.color = MUTED
            continue
        trace.marker.color = COMMUNITY_RAMP[step % len(COMMUNITY_RAMP)]
        step += 1
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
            x=centres,
            y=counts,
            width=np.diff(edges),
            marker={"color": INK, "line": {"width": 0}},
            hovertemplate="%{x:.3g}: %{y}<extra></extra>",
            name="count",
        )
    )
    figure.add_vline(x=median, line={"color": ACCENT, "width": 1})
    figure.add_annotation(
        x=np.log10(median),
        y=1,
        yref="paper",
        text=f"median {median:.3g}",
        showarrow=False,
        xanchor="left",
        font={"family": FONT_MONO, "size": TYPE_12, "color": ACCENT},
    )
    slate(figure, CHART_HEIGHT)
    figure.update_xaxes(type="log", title_text=x_label)
    figure.update_yaxes(title_text="count")
    return figure


def stellar_mass_histogram(catalogue: pd.DataFrame) -> go.Figure | None:
    return log_histogram(positive_values(catalogue, MASS_COLUMN), MASS_LABEL)


def effective_radius_histogram(catalogue: pd.DataFrame) -> go.Figure | None:
    return log_histogram(positive_values(catalogue, RADIUS_COLUMN), RADIUS_LABEL)


def mass_radius_scatter(catalogue: pd.DataFrame) -> go.Figure | None:
    """Mass against radius on log axes, coloured by completeness on the ink scale; ``None`` without both measures."""
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
    slate(figure, CHART_HEIGHT)
    figure.update_layout(coloraxis_colorbar_title_text="completeness %")
    figure.update_xaxes(type="log", title_text=RADIUS_LABEL)
    figure.update_yaxes(type="log", title_text=MASS_LABEL)
    return figure
