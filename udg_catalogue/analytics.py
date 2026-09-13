from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import seaborn as sns
from matplotlib.figure import Figure

MASS_COLUMN = "stellar_mass_solar"
RADIUS_COLUMN = "effective_radius_kpc"
COMPLETENESS_COLUMN = "completeness_pct"
MASS_LABEL = r"Stellar Mass ($M_\odot$)"
RADIUS_LABEL = r"$R_{eff}$ [kpc]"
PLOT_STYLE = "darkgrid"


def _positive_values(catalogue: pd.DataFrame, column: str) -> pd.Series:
    if column not in catalogue.columns:
        return pd.Series(dtype=float)
    values = pd.to_numeric(catalogue[column], errors="coerce")
    return values[values > 0]


def _histogram(values: pd.Series, title: str, x_label: str, color: str) -> Figure | None:
    if values.empty:
        return None
    with sns.axes_style(PLOT_STYLE):
        figure = Figure(figsize=(8, 5))
        axes = figure.subplots()
    sns.histplot(values, log_scale=True, kde=False, color=color, ax=axes)
    axes.set_title(title)
    axes.set_xlabel(x_label)
    axes.set_ylabel("Count")
    figure.tight_layout()
    return figure


def stellar_mass_histogram(catalogue: pd.DataFrame) -> Figure | None:
    return _histogram(
        _positive_values(catalogue, MASS_COLUMN),
        "Stellar Mass Distribution (Solar Masses)",
        MASS_LABEL,
        "purple",
    )


def effective_radius_histogram(catalogue: pd.DataFrame) -> Figure | None:
    return _histogram(
        _positive_values(catalogue, RADIUS_COLUMN),
        "Effective Radius Distribution",
        RADIUS_LABEL,
        "teal",
    )


def mass_radius_scatter(catalogue: pd.DataFrame) -> Figure | None:
    if not {MASS_COLUMN, RADIUS_COLUMN, COMPLETENESS_COLUMN}.issubset(catalogue.columns):
        return None
    data = catalogue.assign(
        **{
            MASS_COLUMN: pd.to_numeric(catalogue[MASS_COLUMN], errors="coerce"),
            RADIUS_COLUMN: pd.to_numeric(catalogue[RADIUS_COLUMN], errors="coerce"),
        }
    )
    data = data[(data[MASS_COLUMN] > 0) & (data[RADIUS_COLUMN] > 0)]
    if data.empty:
        return None
    with sns.axes_style(PLOT_STYLE):
        figure = Figure(figsize=(10, 5))
        axes = figure.subplots()
    sns.scatterplot(
        data=data,
        x=RADIUS_COLUMN,
        y=MASS_COLUMN,
        hue=COMPLETENESS_COLUMN,
        palette="viridis",
        alpha=0.7,
        ax=axes,
    )
    axes.set_xscale("log")
    axes.set_yscale("log")
    axes.set_title("Stellar Mass vs Effective Radius")
    axes.set_xlabel(RADIUS_LABEL)
    axes.set_ylabel(MASS_LABEL)
    axes.legend(title="Completeness %", loc="upper left", bbox_to_anchor=(1, 1))
    figure.tight_layout()
    return figure


REPORT_FIGURES: dict[str, Callable[[pd.DataFrame], Figure | None]] = {
    "stellar_mass_dist.png": stellar_mass_histogram,
    "radius_dist.png": effective_radius_histogram,
    "mass_vs_radius.png": mass_radius_scatter,
}


def generate_analytics_report(
    catalogue: pd.DataFrame,
    output_dir: Path,
    log: Callable[[str], None],
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for file_name, build_figure in REPORT_FIGURES.items():
        figure = build_figure(catalogue)
        if figure is None:
            log(f"Analytics figure skipped for lack of data: {file_name}")
            continue
        destination = output_dir / file_name
        figure.savefig(destination, dpi=300)
        written.append(destination)
    log(f"Analytics report written to {output_dir}")
    return written
