from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from udg_catalogue.astrometry import UNKNOWN_CONSTELLATION, cartesian_coordinates
from udg_catalogue.config import KEY_COLUMN

SPATIAL_COLUMNS: tuple[str, ...] = ("ra", "dec", "distance_mpc")
DARK_MATTER_COLOR_COLUMN = "dark_matter_color"
MISSING_VALUE = "N/A"
HOVER_COLUMNS: tuple[str, ...] = (
    "hover_constellation",
    "hover_cluster",
    "hover_completeness",
    "hover_ra",
    "hover_dec",
    "hover_distance",
    "hover_radius",
    "hover_mass",
    "hover_dark_matter",
)
HOVER_TEMPLATE = (
    "<b>%{hovertext}</b><br><br>"
    "<b>Constellation:</b> %{customdata[0]}<br>"
    "<b>Cluster Status:</b> %{customdata[1]}<br>"
    "<b>Data Completeness:</b> %{customdata[2]}<br>"
    "--------------------------------<br>"
    "<b>Coordinates:</b> RA %{customdata[3]} | Dec %{customdata[4]}<br>"
    "<b>Distance:</b> %{customdata[5]}<br>"
    "<b>Effective Radius (R_eff):</b> %{customdata[6]}<br>"
    "<b>Stellar Mass:</b> %{customdata[7]}<br>"
    "<b>Dark Matter Fraction:</b> %{customdata[8]}<extra></extra>"
)
GRID_COLOR = "#1e293b"


def _column(frame: pd.DataFrame, name: str, default: Any) -> pd.Series:
    return frame[name] if name in frame.columns else pd.Series(default, index=frame.index)


def _numeric(frame: pd.DataFrame, name: str) -> pd.Series:
    return pd.to_numeric(_column(frame, name, np.nan), errors="coerce")


def _formatted(values: pd.Series, template: str, scale: float = 1.0) -> pd.Series:
    return values.map(lambda value: MISSING_VALUE if pd.isna(value) else template.format(value * scale))


def cluster_label(cluster_id: Any) -> str:
    if pd.isna(cluster_id) or cluster_id == -1:
        return "Single / Unclustered"
    return f"Cluster #{int(cluster_id)}"


def prepare_map_frame(catalogue: pd.DataFrame) -> pd.DataFrame:
    if not set(SPATIAL_COLUMNS).issubset(catalogue.columns):
        return catalogue.iloc[0:0].copy()
    frame = catalogue.copy()
    for column in SPATIAL_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=list(SPATIAL_COLUMNS))
    frame = frame[frame["distance_mpc"] >= 0]
    if frame.empty:
        return frame

    dark_matter = _numeric(frame, "dark_matter_fraction").clip(0.0, 1.0)
    frame["dark_matter_fraction"] = dark_matter
    frame[DARK_MATTER_COLOR_COLUMN] = dark_matter.fillna(0.0)

    positions = cartesian_coordinates(frame["ra"], frame["dec"], np.sqrt(frame["distance_mpc"]))
    frame["x"], frame["y"], frame["z"] = positions[:, 0], positions[:, 1], positions[:, 2]
    frame["size_visual"] = np.sqrt(_numeric(frame, "effective_radius_kpc").fillna(1.0).clip(lower=0.0)) * 5

    frame["hover_constellation"] = _column(frame, "constellation", UNKNOWN_CONSTELLATION).fillna(UNKNOWN_CONSTELLATION)
    frame["hover_cluster"] = _column(frame, "cluster_id", -1).map(cluster_label)
    frame["hover_completeness"] = _formatted(_numeric(frame, "completeness_pct"), "{:.1f}%")
    frame["hover_ra"] = _formatted(frame["ra"], "{:.4f}°")
    frame["hover_dec"] = _formatted(frame["dec"], "{:.4f}°")
    frame["hover_distance"] = _formatted(frame["distance_mpc"], "{:.2f} Mpc")
    frame["hover_radius"] = _formatted(_numeric(frame, "effective_radius_kpc"), "{:.2f} kpc")
    frame["hover_mass"] = _formatted(_numeric(frame, "stellar_mass_solar"), "{:.2e} M☉")
    frame["hover_dark_matter"] = _formatted(dark_matter, "{:.1f}%", scale=100.0)
    return frame


def build_3d_figure(
    map_frame: pd.DataFrame,
    color_column: str = DARK_MATTER_COLOR_COLUMN,
    color_label: str = "DM Fraction",
    color_range: Sequence[float] | None = (0.0, 1.0),
    title: str | None = None,
) -> go.Figure:
    figure = px.scatter_3d(
        map_frame,
        x="x",
        y="y",
        z="z",
        color=color_column,
        size="size_visual",
        hover_name=KEY_COLUMN,
        custom_data=list(HOVER_COLUMNS),
        color_continuous_scale="Viridis",
        range_color=list(color_range) if color_range is not None else None,
        title=title or f"3D Distribution of Ultra-Diffuse Galaxies (N = {len(map_frame)})",
        labels={color_column: color_label},
    )
    figure.update_traces(
        marker={"sizemode": "diameter", "sizeref": 1, "sizemin": 3},
        hovertemplate=HOVER_TEMPLATE,
    )
    figure.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b0f19",
        plot_bgcolor="#0b0f19",
        scene={
            "xaxis": {"gridcolor": GRID_COLOR, "title": "X Position [Mpc]"},
            "yaxis": {"gridcolor": GRID_COLOR, "title": "Y Position [Mpc]"},
            "zaxis": {"gridcolor": GRID_COLOR, "title": "Z Position [Mpc]"},
            "bgcolor": "#0a0f1e",
            "aspectmode": "cube",
        },
        margin={"l": 0, "r": 0, "b": 0, "t": 50},
    )
    return figure


def write_3d_map(catalogue: pd.DataFrame, destination: Path, log: Callable[[str], None]) -> bool:
    map_frame = prepare_map_frame(catalogue)
    if map_frame.empty:
        log("3D map skipped: no galaxies have RA, Dec and distance")
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    build_3d_figure(map_frame).write_html(destination)
    log(f"3D map written to {destination}")
    return True
