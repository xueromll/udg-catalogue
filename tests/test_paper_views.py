import numpy as np
from sci_etl_core.search import (
    DiscoveryGraph,
    FusedHit,
    GraphEdge,
    GraphNode,
    QueryChip,
    Snippet,
    describe,
    parse_query,
)

from udg_catalogue.paper_views import (
    COMMUNITY_COLORS,
    DEFAULT_EDGE_STYLE,
    author_line,
    build_graph_figure,
    community_colors,
    describe_chip,
    describe_query,
    escape_markdown,
    graph_table,
    highlight_markdown,
    match_label,
    node_hover,
    paper_url,
    publication_year,
    spring_layout,
)

SEED = GraphNode(
    "2601.00001",
    "Dragonfly 44 <revisited>",
    degree=2,
    community=7,
    metadata={"year": "2016", "authors": ["A", "B", "C", "D"]},
)
NEIGHBOUR = GraphNode("2601.00002", "NGC 1052-DF2", degree=1, community=7, metadata={"authors": ["E"]})
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


def test_escape_markdown_neutralises_markup_and_math():
    assert escape_markdown("A $10^{8}$ M_sun *galaxy*\n [link]") == r"A \$10^\{8\}\$ M\_sun \*galaxy\* \[link\]"


def test_highlight_markdown_bolds_each_match_once():
    snippet = Snippet("body", "dark matter in DF2", ((0, 4), (2, 6), (15, 18)))

    assert highlight_markdown(snippet) == "**dark** matter in **DF2**"


def test_match_label_names_the_legs_that_found_a_hit():
    assert match_label(FusedHit("a", 1.0, lexical_rank=2)) == "keyword #2"
    assert match_label(FusedHit("a", 1.0, semantic_rank=4)) == "related passage, meaning #4"
    assert match_label(FusedHit("a", 1.0, lexical_rank=1, semantic_rank=3)) == "keyword #1, meaning #3"


def test_describe_chip_shows_each_query_construct():
    assert describe_chip(QueryChip("dark matter", phrase=True)) == '"dark matter"'
    assert describe_chip(QueryChip("photometr", prefix=True, fields=("title",))) == "title:photometr*"
    assert describe_chip(QueryChip("simulation", negated=True)) == "NOT simulation"
    assert describe_chip(QueryChip("dwarf halo", near=5)) == "NEAR(dwarf halo, 5)"


def test_describe_query_joins_the_parsed_chips():
    assert describe_query(describe(parse_query('"dark matter" -simulation'))) == '"dark matter" · NOT simulation'


def test_paper_details():
    assert paper_url("2601.00001v2") == "https://arxiv.org/abs/2601.00001v2"
    assert publication_year({"year": "2016"}) == "2016"
    assert publication_year({}) == "n.d."
    assert author_line({"authors": ["A", "B", "C", "D"]}) == "A, B, C et al."
    assert author_line({"authors": ["A", "B"]}) == "A, B"
    assert author_line({}) == ""


def test_spring_layout_is_deterministic_and_pulls_linked_nodes_together():
    node_ids = ["a", "b", "c", "d"]
    edges = [GraphEdge("a", "b", 1.0, "semantic"), GraphEdge("a", "missing", 1.0, "semantic")]

    positions = spring_layout(node_ids, edges)

    assert positions.shape == (4, 2)
    np.testing.assert_array_equal(positions, spring_layout(node_ids, edges))
    linked = np.linalg.norm(positions[0] - positions[1])
    unlinked = np.linalg.norm(positions[2] - positions[3])
    assert linked < unlinked


def test_spring_layout_handles_tiny_graphs():
    assert spring_layout([], []).shape == (0, 2)
    np.testing.assert_array_equal(spring_layout(["a"], []), np.zeros((1, 2)))
    assert spring_layout(["a", "b"], []).shape == (2, 2)


def test_community_colors_follow_first_appearance():
    assert community_colors(GRAPH.nodes) == [COMMUNITY_COLORS[0], COMMUNITY_COLORS[0], COMMUNITY_COLORS[1]]


def test_node_hover_escapes_titles_and_falls_back_to_the_id():
    assert "Dragonfly 44 &lt;revisited&gt;" in node_hover(SEED)
    assert "A, B, C et al." in node_hover(SEED)
    assert node_hover(OUTLIER).startswith("<b>2601.00003</b>")


def test_graph_figure_draws_each_edge_kind_and_outlines_the_seed():
    figure = build_graph_figure(GRAPH)

    assert [trace.name for trace in figure.data] == [
        "citation",
        "Shared authors and categories",
        "Similar content",
        "Papers",
    ]
    assert figure.data[0].line.dash == DEFAULT_EDGE_STYLE[1]
    papers = figure.data[-1]
    assert list(papers.customdata) == ["2601.00001", "2601.00002", "2601.00003"]
    assert list(papers.marker.line.width) == [3, 0.5, 0.5]
    assert list(papers.marker.size) == [18, 15, 15]


def test_graph_figure_of_an_empty_graph_has_only_the_node_trace():
    figure = build_graph_figure(DiscoveryGraph((), (), None, True))

    assert len(figure.data) == 1


def test_graph_table_lists_best_connected_papers_first():
    rows = graph_table(GRAPH)

    assert [row["arxiv"] for row in rows] == [
        "https://arxiv.org/abs/2601.00001",
        "https://arxiv.org/abs/2601.00002",
        "https://arxiv.org/abs/2601.00003",
    ]
    assert rows[0] == {
        "title": "Dragonfly 44 <revisited>",
        "year": "2016",
        "authors": "A, B, C et al.",
        "community": 7,
        "links": 2,
        "arxiv": "https://arxiv.org/abs/2601.00001",
    }
