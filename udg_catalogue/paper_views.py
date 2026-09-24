from __future__ import annotations

import html
import re
from collections.abc import Sequence
from typing import Any

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from sci_etl_core.search import DiscoveryGraph, FusedHit, GraphEdge, GraphNode, QueryChip, Snippet

ARXIV_ABSTRACT_URL = "https://arxiv.org/abs/{record_id}"
MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>$~])")
WHITESPACE = re.compile(r"\s+")
EDGE_STYLES: dict[str, tuple[str, str]] = {"semantic": ("#94a3b8", "solid"), "metadata": ("#f59e0b", "dot")}
DEFAULT_EDGE_STYLE = ("#64748b", "dash")
EDGE_LABELS: dict[str, str] = {"semantic": "Similar content", "metadata": "Shared authors and categories"}
COMMUNITY_COLORS: tuple[str, ...] = tuple(px.colors.qualitative.Plotly)
BACKGROUND = "#0b0f19"
HIDDEN_AXIS: dict[str, Any] = {"visible": False, "showgrid": False, "zeroline": False}
LAYOUT_ITERATIONS = 120
AUTHORS_SHOWN = 3


def escape_markdown(text: str) -> str:
    return MARKDOWN_SPECIAL.sub(r"\\\1", WHITESPACE.sub(" ", text))


def highlight_markdown(snippet: Snippet) -> str:
    parts: list[str] = []
    cursor = 0
    for start, end in sorted(snippet.highlights):
        if start < cursor:
            continue
        parts.append(escape_markdown(snippet.text[cursor:start]))
        parts.append(f"**{escape_markdown(snippet.text[start:end])}**")
        cursor = end
    parts.append(escape_markdown(snippet.text[cursor:]))
    return "".join(parts)


def match_label(hit: FusedHit) -> str:
    if hit.lexical_rank is None:
        return f"related passage, meaning #{hit.semantic_rank}"
    if hit.semantic_rank is None:
        return f"keyword #{hit.lexical_rank}"
    return f"keyword #{hit.lexical_rank}, meaning #{hit.semantic_rank}"


def describe_chip(chip: QueryChip) -> str:
    text = f'"{chip.text}"' if chip.phrase else chip.text
    if chip.near is not None:
        text = f"NEAR({chip.text}, {chip.near})"
    if chip.prefix:
        text = f"{text}*"
    if chip.fields:
        text = f"{','.join(chip.fields)}:{text}"
    return f"NOT {text}" if chip.negated else text


def describe_query(chips: Sequence[QueryChip]) -> str:
    return " · ".join(describe_chip(chip) for chip in chips)


def paper_url(record_id: str) -> str:
    return ARXIV_ABSTRACT_URL.format(record_id=record_id)


def publication_year(metadata: dict[str, Any]) -> str:
    return str(metadata.get("year", "")) or "n.d."


def author_line(metadata: dict[str, Any]) -> str:
    authors = [str(author) for author in metadata.get("authors", []) or []]
    if len(authors) > AUTHORS_SHOWN:
        return f"{', '.join(authors[:AUTHORS_SHOWN])} et al."
    return ", ".join(authors)


def spring_layout(
    node_ids: Sequence[str],
    edges: Sequence[GraphEdge],
    iterations: int = LAYOUT_ITERATIONS,
    seed: int = 0,
) -> np.ndarray:
    count = len(node_ids)
    if count < 2:
        return np.zeros((count, 2))
    positions = np.random.default_rng(seed).uniform(-1.0, 1.0, (count, 2))
    index = {record_id: position for position, record_id in enumerate(node_ids)}
    linked = [edge for edge in edges if edge.source in index and edge.target in index]
    pairs = np.array([(index[edge.source], index[edge.target]) for edge in linked], dtype=int).reshape(-1, 2)
    weights = np.array([edge.weight for edge in linked], dtype=float).reshape(-1, 1)
    spacing = 1.0 / np.sqrt(count)
    temperature = 0.1
    for _ in range(iterations):
        delta = positions[:, None, :] - positions[None, :, :]
        distance = np.maximum(np.linalg.norm(delta, axis=-1), 1e-3)
        displacement = ((spacing**2 / distance**2)[..., None] * delta).sum(axis=1)
        if len(pairs):
            stretch = positions[pairs[:, 0]] - positions[pairs[:, 1]]
            pull = stretch * np.linalg.norm(stretch, axis=1, keepdims=True) / spacing * weights
            np.add.at(displacement, pairs[:, 0], -pull)
            np.add.at(displacement, pairs[:, 1], pull)
        length = np.maximum(np.linalg.norm(displacement, axis=1, keepdims=True), 1e-9)
        positions = positions + displacement / length * np.minimum(length, temperature)
        temperature *= 0.97
    return positions


def community_colors(nodes: Sequence[GraphNode]) -> list[str]:
    order = {community: rank for rank, community in enumerate(dict.fromkeys(node.community for node in nodes))}
    return [COMMUNITY_COLORS[order[node.community] % len(COMMUNITY_COLORS)] for node in nodes]


def node_hover(node: GraphNode) -> str:
    title = html.escape(" ".join(node.title.split()) or node.record_id)
    authors = html.escape(author_line(node.metadata))
    return (
        f"<b>{title}</b><br>{html.escape(node.record_id)} · {publication_year(node.metadata)}<br>"
        f"{authors}<br>Community {node.community} · {node.degree} links"
    )


def build_graph_figure(graph: DiscoveryGraph) -> go.Figure:
    node_ids = [node.record_id for node in graph.nodes]
    positions = spring_layout(node_ids, graph.edges)
    where = {record_id: positions[position] for position, record_id in enumerate(node_ids)}
    figure = go.Figure()
    for kind in sorted({edge.kind for edge in graph.edges}):
        xs: list[float | None] = []
        ys: list[float | None] = []
        for edge in graph.edges:
            if edge.kind == kind:
                xs += [float(where[edge.source][0]), float(where[edge.target][0]), None]
                ys += [float(where[edge.source][1]), float(where[edge.target][1]), None]
        color, dash = EDGE_STYLES.get(kind, DEFAULT_EDGE_STYLE)
        figure.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line={"color": color, "width": 1, "dash": dash},
                hoverinfo="skip",
                name=EDGE_LABELS.get(kind, kind),
            )
        )
    figure.add_trace(
        go.Scatter(
            x=positions[:, 0] if len(node_ids) else [],
            y=positions[:, 1] if len(node_ids) else [],
            mode="markers",
            marker={
                "size": [12 + 3 * node.degree for node in graph.nodes],
                "color": community_colors(graph.nodes),
                "line": {
                    "color": "white",
                    "width": [3 if node.record_id == graph.seed_record_id else 0.5 for node in graph.nodes],
                },
            },
            text=[node_hover(node) for node in graph.nodes],
            hovertemplate="%{text}<extra></extra>",
            customdata=node_ids,
            name="Papers",
        )
    )
    figure.update_layout(
        template="plotly_dark",
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        xaxis=HIDDEN_AXIS,
        yaxis=HIDDEN_AXIS,
        margin={"l": 0, "r": 0, "b": 0, "t": 30},
        legend={"orientation": "h"},
    )
    return figure


def graph_table(graph: DiscoveryGraph) -> list[dict[str, Any]]:
    return [
        {
            "title": " ".join(node.title.split()),
            "year": publication_year(node.metadata),
            "authors": author_line(node.metadata),
            "community": node.community,
            "links": node.degree,
            "arxiv": paper_url(node.record_id),
        }
        for node in sorted(graph.nodes, key=lambda node: (-node.degree, node.record_id))
    ]
