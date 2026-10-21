"""The graph canvas: a restyled Plotly scatter of the discovery graph.

Nodes are filled by community with the categorical palette and sized by degree,
the seed is the one accent element, hits keep full ink and everything else is
dimmed, and edges are drawn per kind so each kind can be switched off. The
layout is the catalogue's spring layout, seeded from the record ids, so the
same graph renders the same way twice.
"""

from __future__ import annotations

import math
import zlib
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import plotly.graph_objects as go
from sci_etl_core.search import DiscoveryGraph, GraphNode

from udg_catalogue.paper_views import node_hover, spring_layout
from udg_catalogue.ui.tokens import (
    ACCENT,
    CANVAS,
    CATEGORICAL,
    DIMMED_ALPHA,
    HALO,
    INK,
    MUTED,
    SEPARATOR,
    plotly_layout,
    rgba,
)

RADIUS_MIN = 3.0
RADIUS_MAX = 14.0
KEY_SIZE = 10
CANVAS_HEIGHT = 560
FULLSCREEN_HEIGHT = 820
HIDDEN_AXIS: dict[str, Any] = {"visible": False, "showgrid": False, "zeroline": False, "fixedrange": False}
KIND_LABELS: dict[str, str] = {"semantic": "semantic", "metadata": "metadata (authors, categories)"}
# Edge kinds differ by dash, so the legend tells them apart; the faint separator is kept for the dense semantic web.
EDGE_STYLES: dict[str, tuple[str, str]] = {"semantic": (SEPARATOR, "solid"), "metadata": (MUTED, "dot")}
DEFAULT_EDGE_STYLE = (MUTED, "dash")
# The legend only names what is drawn (edge kinds and every node colour); the checkboxes above the canvas stay the one way to switch an edge kind off.
LEGEND: dict[str, Any] = {
    "orientation": "h",
    "x": 0,
    "xanchor": "left",
    "y": 0,
    "yanchor": "top",
    "itemsizing": "constant",
    "itemclick": False,
    "itemdoubleclick": False,
}


@dataclass(frozen=True, slots=True)
class CanvasStyle:
    """What the canvas highlights: the hits of the current search, the selected node and the edge kinds drawn."""

    hit_ids: frozenset[str] = field(default_factory=frozenset)
    selected: str | None = None
    kinds_on: frozenset[str] | None = None
    fullscreen: bool = False


def node_radius(degree: int) -> float:
    """``clip(3 + 1.5 * sqrt(degree), 3, 14)`` px, as the token table fixes it."""
    return min(RADIUS_MAX, max(RADIUS_MIN, 3.0 + 1.5 * math.sqrt(max(degree, 0))))


def layout_seed(record_ids: Collection[str]) -> int:
    """A layout seed that depends only on which records are in the graph."""
    return zlib.crc32("\n".join(sorted(record_ids)).encode("utf-8"))


def layout_positions(graph: DiscoveryGraph) -> dict[str, tuple[float, float]]:
    """Deterministic coordinates per record id; every edge shapes the layout, whatever kinds are drawn."""
    node_ids = [node.record_id for node in graph.nodes]
    positions = spring_layout(node_ids, graph.edges, seed=layout_seed(node_ids))
    return {record_id: (float(x), float(y)) for record_id, (x, y) in zip(node_ids, positions, strict=True)}


def edge_kinds(graph: DiscoveryGraph) -> list[str]:
    """The kinds present, semantic first, then metadata, then anything else alphabetically."""
    present = {edge.kind for edge in graph.edges}
    order = {"semantic": 0, "metadata": 1}
    return sorted(present, key=lambda kind: (order.get(kind, 2), kind))


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


def community_ranks(nodes: Sequence[GraphNode]) -> dict[int, int]:
    """Communities ranked by size, largest first; ranks beyond the palette are filled in the muted grey."""
    sizes: dict[int, int] = {}
    for node in nodes:
        sizes[node.community] = sizes.get(node.community, 0) + 1
    ordered = sorted(sizes, key=lambda community: (-sizes[community], community))
    return {community: rank for rank, community in enumerate(ordered)}


def is_dimmed(node: GraphNode, graph: DiscoveryGraph, style: CanvasStyle) -> bool:
    """With a search on screen, everything that is neither a hit, the seed nor the selection is dimmed."""
    if not style.hit_ids:
        return False
    return node.record_id not in style.hit_ids and node.record_id not in {graph.seed_record_id, style.selected}


def node_fill(node: GraphNode, graph: DiscoveryGraph, style: CanvasStyle, ranks: Mapping[int, int]) -> str:
    if node.record_id == graph.seed_record_id:
        return ACCENT
    if is_dimmed(node, graph, style):
        return rgba(MUTED, DIMMED_ALPHA)
    rank = ranks[node.community]
    return CATEGORICAL[rank] if rank < len(CATEGORICAL) else MUTED


def node_stroke(node: GraphNode, graph: DiscoveryGraph, style: CanvasStyle) -> tuple[str, float]:
    """``(colour, width)`` of the node outline: a halo for the seed and the selection, 1 px ink otherwise."""
    if node.record_id == graph.seed_record_id:
        return HALO, 4.0
    if node.record_id == style.selected:
        return HALO, 3.0
    if is_dimmed(node, graph, style):
        return rgba(MUTED, DIMMED_ALPHA), 1.0
    return INK, 1.0


def legend_key(name: str, fill: str, stroke: tuple[str, float] = (INK, 1.0)) -> go.Scatter:
    """An empty trace that only puts one node look, with its name, into the legend."""
    colour, width = stroke
    return go.Scatter(
        x=[None],
        y=[None],
        mode="markers",
        marker={"size": KEY_SIZE, "color": fill, "line": {"color": colour, "width": width}},
        hoverinfo="skip",
        name=name,
    )


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def legend_keys(graph: DiscoveryGraph, style: CanvasStyle, ranks: Mapping[int, int]) -> list[go.Scatter]:
    """One key per node look on the canvas, in the order ``node_fill`` decides it: the chosen paper, the selection,
    each palette community with its size, the smaller communities in grey, and the papers a search dims."""
    keys: list[go.Scatter] = []
    record_ids = {node.record_id for node in graph.nodes}
    if graph.seed_record_id in record_ids:
        keys.append(legend_key("chosen paper", ACCENT, (HALO, 4.0)))
    if style.selected in record_ids and style.selected != graph.seed_record_id:
        keys.append(legend_key("selected paper", CANVAS, (HALO, 3.0)))
    drawn = [node for node in graph.nodes if node.record_id != graph.seed_record_id and not is_dimmed(node, graph, style)]
    sizes = Counter(node.community for node in graph.nodes)
    shown = {node.community for node in drawn}
    for community, rank in sorted(ranks.items(), key=lambda item: item[1]):
        if rank < len(CATEGORICAL) and community in shown:
            keys.append(legend_key(f"community {community} · {plural(sizes[community], 'paper')}", CATEGORICAL[rank]))
    smaller = {community for community in shown if ranks[community] >= len(CATEGORICAL)}
    if smaller:
        keys.append(legend_key("1 smaller community" if len(smaller) == 1 else f"{len(smaller)} smaller communities", MUTED))
    if any(is_dimmed(node, graph, style) for node in graph.nodes):
        keys.append(legend_key("not in the search results", rgba(MUTED, DIMMED_ALPHA), (rgba(MUTED, DIMMED_ALPHA), 1.0)))
    return keys


def build_canvas(graph: DiscoveryGraph, style: CanvasStyle = CanvasStyle()) -> go.Figure:
    """The figure: one line trace per drawn edge kind, one empty key per node look, the node trace last so it draws on
    top, and a legend below the canvas naming every edge kind and node colour; no title or colour bar."""
    where = layout_positions(graph)
    ranks = community_ranks(graph.nodes)
    figure = go.Figure()
    for kind in edge_kinds(graph):
        if style.kinds_on is not None and kind not in style.kinds_on:
            continue
        xs: list[float | None] = []
        ys: list[float | None] = []
        for edge in graph.edges:
            if edge.kind == kind:
                xs += [where[edge.source][0], where[edge.target][0], None]
                ys += [where[edge.source][1], where[edge.target][1], None]
        colour, dash = EDGE_STYLES.get(kind, DEFAULT_EDGE_STYLE)
        figure.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line={"color": colour, "width": 1, "dash": dash},
                hoverinfo="skip",
                name=kind_label(kind),
            )
        )
    figure.add_traces(legend_keys(graph, style, ranks))
    strokes =[node_stroke(node, graph, style) for node in graph.nodes]
    figure.add_trace(
        go.Scatter(
            x=[where[node.record_id][0] for node in graph.nodes],
            y=[where[node.record_id][1] for node in graph.nodes],
            mode="markers",
            marker={
                "size": [2 * node_radius(node.degree) for node in graph.nodes],
                "color": [node_fill(node, graph, style, ranks) for node in graph.nodes],
                "line": {"color": [colour for colour, _width in strokes], "width": [width for _colour, width in strokes]},
            },
            text=[node_hover(node) for node in graph.nodes],
            hovertemplate="%{text}<extra></extra>",
            customdata=[node.record_id for node in graph.nodes],
            name="papers",
            showlegend=False,
        )
    )
    figure.update_layout(
        plotly_layout(
            xaxis=HIDDEN_AXIS,
            yaxis=dict(HIDDEN_AXIS, scaleanchor="x"),
            margin={"l": 0, "r": 0, "t": 0, "b": 0},
            height=FULLSCREEN_HEIGHT if style.fullscreen else CANVAS_HEIGHT,
            showlegend=True,
            legend=dict(plotly_layout()["legend"], **LEGEND),
            dragmode="pan",
            clickmode="event+select",
        )
    )
    return figure


def canvas_caption(graph: DiscoveryGraph, style: CanvasStyle) -> str:
    """``n nodes · m edges · k dimmed`` for the status line under the canvas."""
    dimmed = sum(is_dimmed(node, graph, style) for node in graph.nodes)
    drawn = [edge for edge in graph.edges if style.kinds_on is None or edge.kind in style.kinds_on]
    return f"{len(graph.nodes)} nodes · {len(drawn)} edges · {dimmed} dimmed · seed {graph.seed_record_id}"


def selected_from_state(state: Any) -> str | None:
    """The record id of the first point of a Plotly selection state, or ``None`` when nothing is selected."""
    selection = state.get("selection") if isinstance(state, Mapping) else getattr(state, "selection", None)
    if not selection:
        return None
    points = selection.get("points") if isinstance(selection, Mapping) else getattr(selection, "points", None)
    for point in points or ():
        record_id = point.get("customdata") if isinstance(point, Mapping) else getattr(point, "customdata", None)
        if record_id:
            return str(record_id[0] if isinstance(record_id, (list, tuple, np.ndarray)) else record_id)
    return None


def node_options(graph: DiscoveryGraph) -> list[str]:
    """Record ids for the selection fallback, best connected first."""
    return [node.record_id for node in sorted(graph.nodes, key=lambda node: (-node.degree, node.record_id))]


def node_label(graph: DiscoveryGraph, record_id: str) -> str:
    """``id  title`` for the fallback selectbox; the id alone when the record is not in the graph."""
    for node in graph.nodes:
        if node.record_id == record_id:
            title = " ".join(node.title.split())
            return f"{record_id}  {title[:48]}" if title else record_id
    return record_id
