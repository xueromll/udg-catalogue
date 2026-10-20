from types import SimpleNamespace

import numpy as np
import pytest
from sci_etl_core.search import DiscoveryGraph, GraphEdge, GraphNode

from udg_catalogue.ui.graph import (
    CANVAS_HEIGHT,
    FULLSCREEN_HEIGHT,
    CanvasStyle,
    build_canvas,
    canvas_caption,
    community_ranks,
    edge_kinds,
    is_dimmed,
    kind_label,
    layout_positions,
    layout_seed,
    node_fill,
    node_label,
    node_options,
    node_radius,
    node_stroke,
    selected_from_state,
)
from udg_catalogue.ui.tokens import ACCENT, CATEGORICAL, HALO, INK, MUTED, SEPARATOR, rgba

SEED = GraphNode("2601.00001", "Dragonfly 44 <revisited>", degree=2, community=7, metadata={"year": "2016"})
NEIGHBOUR = GraphNode("2601.00002", "NGC 1052-DF2", degree=1, community=7)
OUTLIER = GraphNode("2601.00003", "", degree=1, community=3)
GRAPH = DiscoveryGraph(
    nodes=(SEED, NEIGHBOUR, OUTLIER),
    edges=(
        GraphEdge("2601.00001", "2601.00002", 0.9, "semantic"),
        GraphEdge("2601.00001", "2601.00003", 0.5, "metadata"),
        GraphEdge("2601.00002", "2601.00003", 0.4, "citation"),
    ),
    seed_record_id="2601.00001",
    communities_converged=True,
)
DIMMED = rgba(MUTED, 0.4)


def test_node_radius_follows_the_token_formula_within_its_clip():
    assert node_radius(0) == 3
    assert node_radius(4) == 6
    assert node_radius(-1) == 3
    assert node_radius(1000) == 14


def test_layout_depends_only_on_the_records_in_the_graph():
    assert layout_seed(["a", "b"]) == layout_seed(["b", "a"]) != layout_seed(["a"])

    positions = layout_positions(GRAPH)

    assert list(positions) == ["2601.00001", "2601.00002", "2601.00003"]
    assert positions == layout_positions(GRAPH)
    assert all(isinstance(value, float) for point in positions.values() for value in point)


def test_edge_kinds_put_semantic_first_then_metadata_then_the_rest():
    assert edge_kinds(GRAPH) == ["semantic", "metadata", "citation"]
    assert kind_label("metadata") == "metadata (authors, categories)"
    assert kind_label("citation") == "citation"


def test_community_ranks_order_by_size_largest_first():
    assert community_ranks(GRAPH.nodes) == {7: 0, 3: 1}
    nodes = [GraphNode(str(index), community=index) for index in range(8)]
    assert community_ranks(nodes) == {index: index for index in range(8)}


def test_dimming_applies_only_with_hits_on_screen_and_spares_seed_and_selection():
    nothing = CanvasStyle()
    hits = CanvasStyle(hit_ids=frozenset({NEIGHBOUR.record_id}))
    picked = CanvasStyle(hit_ids=frozenset({NEIGHBOUR.record_id}), selected=OUTLIER.record_id)

    assert [is_dimmed(node, GRAPH, nothing) for node in GRAPH.nodes] == [False, False, False]
    assert [is_dimmed(node, GRAPH, hits) for node in GRAPH.nodes] == [False, False, True]
    assert [is_dimmed(node, GRAPH, picked) for node in GRAPH.nodes] == [False, False, False]


def test_node_fill_and_stroke_follow_the_visual_system():
    hits = CanvasStyle(hit_ids=frozenset({NEIGHBOUR.record_id}))
    ranks = community_ranks(GRAPH.nodes)

    assert node_fill(SEED, GRAPH, hits, ranks) == ACCENT
    assert node_fill(NEIGHBOUR, GRAPH, hits, ranks) == CATEGORICAL[0]
    assert node_fill(OUTLIER, GRAPH, hits, ranks) == DIMMED
    assert node_fill(OUTLIER, GRAPH, CanvasStyle(), ranks) == CATEGORICAL[1]
    seventh = GraphNode("2601.00009", community=99)
    assert node_fill(seventh, GRAPH, CanvasStyle(), {**ranks, 99: len(CATEGORICAL)}) == MUTED
    assert node_stroke(SEED, GRAPH, hits) == (HALO, 4.0)
    assert node_stroke(OUTLIER, GRAPH, CanvasStyle(selected=OUTLIER.record_id)) == (HALO, 3.0)
    assert node_stroke(OUTLIER, GRAPH, hits) == (DIMMED, 1.0)
    assert node_stroke(NEIGHBOUR, GRAPH, hits) == (INK, 1.0)


def test_canvas_draws_one_trace_per_drawn_kind_and_one_for_the_nodes():
    figure = build_canvas(GRAPH)

    assert [trace.name for trace in figure.data] == ["semantic", "metadata", "citation", "papers"]
    assert all(trace.line.color == SEPARATOR for trace in figure.data[:-1])
    papers = figure.data[-1]
    assert list(papers.customdata) == ["2601.00001", "2601.00002", "2601.00003"]
    assert list(papers.marker.size) == [2 * node_radius(2), 9, 9]
    assert list(papers.marker.color) == [ACCENT, CATEGORICAL[0], CATEGORICAL[1]]
    assert list(papers.marker.line.width) == [4, 1, 1]
    assert figure.layout.height == CANVAS_HEIGHT
    assert figure.layout.title.text is None
    assert figure.layout.showlegend is False
    assert figure.layout.xaxis.visible is False


def test_canvas_honours_edge_kind_toggles_and_fullscreen():
    figure = build_canvas(GRAPH, CanvasStyle(kinds_on=frozenset({"semantic"}), fullscreen=True))

    assert [trace.name for trace in figure.data] == ["semantic", "papers"]
    assert figure.layout.height == FULLSCREEN_HEIGHT
    assert len(build_canvas(DiscoveryGraph((), (), None, True)).data) == 1


def test_canvas_caption_counts_nodes_drawn_edges_and_dimmed_nodes():
    style = CanvasStyle(hit_ids=frozenset({NEIGHBOUR.record_id}), kinds_on=frozenset({"semantic"}))

    assert canvas_caption(GRAPH, style) == "3 nodes · 1 edges · 1 dimmed · seed 2601.00001"
    assert canvas_caption(GRAPH, CanvasStyle()) == "3 nodes · 3 edges · 0 dimmed · seed 2601.00001"


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (None, None),
        ({}, None),
        ({"selection": {"points": []}}, None),
        ({"selection": {"points": [{"customdata": []}, {"customdata": ["2601.00002"]}]}}, "2601.00002"),
        ({"selection": {"points": [{"customdata": "2601.00003"}]}}, "2601.00003"),
        ({"selection": {"points": [{"customdata": np.array(["2601.00001"])}]}}, "2601.00001"),
        (SimpleNamespace(selection=SimpleNamespace(points=[SimpleNamespace(customdata=("x",))])), "x"),
        (SimpleNamespace(selection=None), None),
    ],
)
def test_selected_from_state_reads_the_first_selected_point(state, expected):
    assert selected_from_state(state) == expected


def test_node_options_and_labels_for_the_selection_fallback():
    assert node_options(GRAPH) == ["2601.00001", "2601.00002", "2601.00003"]
    assert node_label(GRAPH, "2601.00001") == "2601.00001  Dragonfly 44 <revisited>"
    assert node_label(GRAPH, "2601.00003") == "2601.00003"
    assert node_label(GRAPH, "missing") == "missing"
