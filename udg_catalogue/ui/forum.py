"""The board frame around every page: tagline, nav strip, breadcrumb, board index, statistics, legend and footer.

The layout follows the bulletin boards of the early 2000s: a site header with
a nav strip, a breadcrumb trail, a board index listing the constellations and
clusters like forums, every section a ruled table under an ink category bar,
alternating row stripes, and a statistics box with a legend closing the page.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from udg_catalogue.astrometry import UNKNOWN_CONSTELLATION
from udg_catalogue.config import KEY_COLUMN
from udg_catalogue.maps import SPATIAL_COLUMNS
from udg_catalogue.ui.inspector import NO_MANIFEST, extraction_stamp

SITE_NAME = "UDG Catalogue"
CRUMB_SEPARATOR = '<span class="udg-crumb-sep">›</span>'
CONFIRMED = "Confirmed"
BOARD_ROWS = 8
LAMP_ON = "■"
LAMP_OFF = "□"
NO_NEAREST = "—"


@dataclass(frozen=True, slots=True)
class BoardRow:
    """One row of the board index: a constellation or a cluster and what the selection holds in it."""

    name: str
    galaxies: int
    confirmed: int
    mapped: int
    nearest: str = NO_NEAREST


def tagline_html(total: int) -> str:
    """The line under the site name: how many galaxies the catalogue holds and where they come from."""
    return (
        f'<div class="udg-tagline">{total:,} galaxies in the catalogue · '
        "ultra-diffuse galaxies extracted from the literature</div>"
    )


def nav_html(views: Sequence[tuple[str, str]], current: str, now: datetime) -> str:
    """The nav strip: one link per ``(label, slug)`` view, the current one unlinked, and the time on the right."""
    links = " · ".join(
        f'<span class="udg-nav-here">{html.escape(label)}</span>'
        if label == current
        else f'<a href="?view={html.escape(slug)}" target="_self">{html.escape(label)}</a>'
        for label, slug in views
    )
    return f'<div class="udg-navbar"><span>{links}</span><span class="udg-now">It is currently {now:%a %b %d, %Y %H:%M}</span></div>'


def breadcrumb_html(crumbs: Sequence[str]) -> str:
    """``UDG Catalogue › Galaxies › Data Table``, the last crumb marked as the current page."""
    last = len(crumbs) - 1
    parts = [
        f'<span class="{"udg-crumb udg-crumb-here" if index == last else "udg-crumb"}">{html.escape(crumb)}</span>'
        for index, crumb in enumerate(crumbs)
    ]
    return f'<div class="udg-crumbs">{CRUMB_SEPARATOR.join(parts)}</div>'


def numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(float("nan"), index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce")


def mapped_mask(frame: pd.DataFrame) -> pd.Series:
    """Which galaxies the 3D map can draw: a position and a non-negative distance."""
    known = pd.concat([numeric(frame, column).notna() for column in SPATIAL_COLUMNS], axis=1).all(axis=1)
    return known & (numeric(frame, "distance_mpc") >= 0)


def confirmed_mask(frame: pd.DataFrame) -> pd.Series:
    if "quality_flag" not in frame.columns:
        return pd.Series(False, index=frame.index)
    return frame["quality_flag"] == CONFIRMED


def place_label(value: Any) -> str:
    return UNKNOWN_CONSTELLATION if pd.isna(value) else str(value)


def board_rows(
    frame: pd.DataFrame, column: str, label: Callable[[Any], str] = place_label, limit: int = BOARD_ROWS
) -> tuple[list[BoardRow], int]:
    """The ``limit`` largest groups of ``column``, largest first, and how many groups stay hidden."""
    if column not in frame.columns or frame.empty:
        return [], 0
    mapped = mapped_mask(frame)
    confirmed = confirmed_mask(frame)
    distance = numeric(frame, "distance_mpc").where(mapped)
    rows = []
    for value, group in frame.groupby(column, dropna=False, sort=False):
        near = distance.loc[group.index].dropna()
        nearest = NO_NEAREST if near.empty else f"{frame.at[near.idxmin(), KEY_COLUMN]} · {near.min():.3g} Mpc"
        rows.append(
            BoardRow(label(value), len(group), int(confirmed.loc[group.index].sum()), int(mapped.loc[group.index].sum()), nearest)
        )
    rows.sort(key=lambda row: (-row.galaxies, row.name))
    return rows[:limit], max(0, len(rows) - limit)


def board_html(heading: str, rows: Sequence[BoardRow], hidden: int, noun: str) -> str:
    """A board index table: a lamp, the group, its counts and its nearest mapped galaxy, then a ``... n more`` row."""
    body = "".join(
        f'<tr><td class="udg-lamp" title="{"has confirmed galaxies" if row.confirmed else "no confirmed galaxy yet"}">'
        f"{LAMP_ON if row.confirmed else LAMP_OFF}</td>"
        f'<td class="udg-board-name">{html.escape(row.name)}</td><td class="udg-num">{row.galaxies:,}</td>'
        f'<td class="udg-num">{row.confirmed:,}</td><td class="udg-num">{row.mapped:,}</td>'
        f'<td class="udg-nearest" title="{html.escape(row.nearest)}">{html.escape(row.nearest)}</td></tr>'
        for row in rows
    )
    if hidden:
        body += f'<tr class="udg-more"><td></td><td colspan="5">... {hidden:,} more {html.escape(noun)}</td></tr>'
    return (
        '<table class="udg-forumline"><thead><tr><th class="udg-lamp"></th>'
        f'<th>{html.escape(heading)}</th><th class="udg-num">Galaxies</th><th class="udg-num">Confirmed</th>'
        f'<th class="udg-num">Mapped</th><th>Nearest</th></tr></thead><tbody>{body}</tbody></table>'
    )


def record_holder(frame: pd.DataFrame, column: str, title: str, unit: str, spec: str) -> str | None:
    """``Largest: DF44 (4.6 kpc)`` for the galaxy with the highest ``column``, or ``None`` without a value."""
    values = numeric(frame, column).dropna()
    if values.empty:
        return None
    return f"{title}: {frame.at[values.idxmax(), KEY_COLUMN]} ({values.max():{spec}} {unit})"


def stats_lines(catalogue: pd.DataFrame, selection: pd.DataFrame, manifest: dict[str, Any] | None) -> list[str]:
    """The statistics box: sizes, quality flags, the mapped share, record holders, then the last build."""
    clusters = numeric(catalogue, "cluster_id")
    lines = [
        (
            f"The catalogue holds {len(catalogue):,} galaxies in {catalogue['constellation'].nunique():,} constellations "
            f"and {clusters[clusters >= 0].nunique():,} clusters; the current selection shows {len(selection):,}."
        )
    ]
    if "quality_flag" in selection.columns and not selection.empty:
        counts = selection["quality_flag"].value_counts()
        lines.append(" · ".join(f"{flag} {count:,}" for flag, count in counts.items()))
    mapped = mapped_mask(selection)
    distance = numeric(selection, "distance_mpc")[mapped]
    median = f" · median distance {distance.median():.3g} Mpc" if mapped.any() else ""
    lines.append(f"With a position and a distance: {int(mapped.sum()):,}{median}")
    holders = [
        holder
        for holder in (
            record_holder(selection, "effective_radius_kpc", "Largest", "kpc", ".3g"),
            record_holder(selection, "stellar_mass_solar", "Most massive", "M☉", ".2e"),
        )
        if holder
    ]
    if holders:
        lines.append(" · ".join(holders))
    if manifest is None:
        lines.append(f"Last build: {NO_MANIFEST}.")
    else:
        stamp = dict(extraction_stamp(manifest))
        lines.append(f"Last build {stamp['built']} · model {stamp['model']} · {stamp['library']}.")
    return lines


def stats_html(lines: Sequence[str]) -> str:
    rows = "".join(f'<div class="udg-stats-row">{html.escape(line)}</div>' for line in lines)
    return f'<div class="udg-stats">{rows}</div>'


def legend_html() -> str:
    """What the board index lamps mean."""
    return (
        f'<div class="udg-legend"><span class="udg-lamp">{LAMP_ON}</span> has confirmed galaxies'
        f'<span class="udg-lamp">{LAMP_OFF}</span> no confirmed galaxy yet</div>'
    )


def footer_html(catalogue_version: str, library_version: str) -> str:
    """The board's closing line: the catalogue version and the library it runs on."""
    return (
        f'<div class="udg-footer">{SITE_NAME} {html.escape(catalogue_version)} · '
        f"powered by sci-etl-core {html.escape(library_version)}</div>"
    )
