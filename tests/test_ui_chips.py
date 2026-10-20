from sci_etl_core.discovery import DiscoveryResult
from sci_etl_core.search import DiscoveryGraph, FusedHit, QueryChip

from udg_catalogue.ui.chips import (
    COMMUNITIES_APPROXIMATE,
    FILTER,
    BannerLine,
    Chip,
    banner_html,
    banner_lines,
    chips_html,
    filter_chips,
    query_chips,
    quiet_html,
    region_html,
    status_html,
    status_line,
)

HITS = (FusedHit("a", 0.5, lexical_rank=1), FusedHit("b", 0.4, semantic_rank=1))


def result(**overrides):
    fields = {
        "query_text": "dark",
        "chips": (QueryChip("dark"),),
        "hits": HITS,
        "graph": None,
        "facets": (),
        "total_matched": 2118,
        "elapsed_ms": 61.4,
    }
    fields.update(overrides)
    return DiscoveryResult(**fields)


def test_query_chips_keep_negation_depth_and_operator_as_state():
    chips = query_chips(
        [
            QueryChip("dark matter", phrase=True, operator="AND", depth=1),
            QueryChip("simulation", negated=True, operator="AND"),
            QueryChip("lensing", negated=True),
        ]
    )

    assert chips == [
        Chip('"dark matter"', depth=1, title="AND"),
        Chip("simulation", negated=True, title="NOT, AND"),
        Chip("lensing", negated=True, title="NOT"),
    ]


def test_filter_chips_name_each_active_filter():
    assert filter_chips() == []
    assert filter_chips(("astro-ph.GA",), (2019, 2019)) == [
        Chip("categories:astro-ph.GA", FILTER, title="categories"),
        Chip("year:2019", FILTER, title="year"),
    ]
    assert filter_chips(years=(2018, 2020)) == [Chip("year:2018-2020", FILTER, title="year")]


def test_chips_html_marks_filters_negations_and_depth_and_escapes_text():
    assert chips_html([]) == ""

    markup = chips_html(
        [Chip("<a>", depth=1, title="AND"), Chip("x", FILTER), Chip("simulation", negated=True)]
    )

    assert markup.startswith('<div class="udg-chips">')
    assert '<span class="udg-chip" style="border-left-width:2px" title="AND">&lt;a&gt;</span>' in markup
    assert '<span class="udg-chip udg-chip-filter">x</span>' in markup
    assert '<span class="udg-chip udg-chip-negated">simulation</span>' in markup


def test_status_line_shows_total_matched_and_elapsed_ms_per_mode():
    assert status_line(result(), "lexical") == "2,118 matched · 2 shown · 61 ms"
    assert status_line(result(), "semantic") == "2 nearest passages · 61 ms"
    assert status_html("1 matched · 2 ms") == '<div class="udg-status">1 matched · 2 ms</div>'


def test_banner_lines_name_failed_legs_first_then_skipped_legs_and_approximations():
    graph = DiscoveryGraph((), (), None, communities_converged=False)

    assert banner_lines(None, None) == []
    assert banner_lines(result(), DiscoveryGraph((), (), None, True)) == []
    assert banner_lines(result(degraded=("semantic", "citation"), skipped=("lexical", "other")), graph) == [
        BannerLine("!", "semantic leg failed: the embeddings could not be queried. Showing keyword results only."),
        BannerLine("!", "citation leg failed: showing the other legs only."),
        BannerLine("i", "keyword leg skipped: the query has nothing the text index can match."),
        BannerLine("i", "other leg skipped: nothing to run."),
        BannerLine("i", COMMUNITIES_APPROXIMATE),
    ]
    assert banner_lines(None, graph) == [BannerLine("i", COMMUNITIES_APPROXIMATE)]


def test_banner_html_is_one_block_with_a_glyph_per_line_or_nothing():
    assert banner_html([]) == ""

    markup = banner_html([BannerLine("!", "semantic <leg> failed")])

    assert markup.startswith('<div class="udg-banner">')
    assert '<span class="udg-banner-glyph">!</span>semantic &lt;leg&gt; failed</span>' in markup


def test_quiet_and_region_fragments_escape_their_text():
    assert quiet_html("a < b") == '<div class="udg-quiet">a &lt; b</div>'
    assert region_html("Hits & more") == '<div class="udg-region">Hits &amp; more</div>'
