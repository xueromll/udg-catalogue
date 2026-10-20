from sci_etl_core.search import FusedHit

from udg_catalogue.ui.hits import hit_html, rank_label


def test_rank_label_writes_both_legs_with_a_dash_for_a_missing_one():
    assert rank_label(FusedHit("a", 1.0, lexical_rank=2)) == "L2 S-"
    assert rank_label(FusedHit("a", 1.0, semantic_rank=4)) == "L- S4"
    assert rank_label(FusedHit("a", 1.0, lexical_rank=1, semantic_rank=3)) == "L1 S3"


def test_hit_html_links_the_title_and_sets_id_year_ranks_and_score_in_the_meta_line():
    hit = FusedHit("2601.00001", 0.03254, lexical_rank=1, title="  A <giant>  disc ", metadata={"year": "2023"})

    markup = hit_html(1, hit, selected="2601.00001")

    assert markup.startswith('<div class="udg-hit-selected">')
    assert '<a href="https://arxiv.org/abs/2601.00001">A &lt;giant&gt; disc</a>' in markup
    assert '<div class="udg-meta">2601.00001 · 2023 · L1 S- · 0.033</div>' in markup


def test_hit_html_falls_back_to_the_id_and_leaves_unselected_rows_plain():
    markup = hit_html(2, FusedHit("2601.00002", 1.0))

    assert markup.startswith("<div><div")
    assert ">2601.00002</a>" in markup
    assert "n.d." in markup
