from datetime import datetime, timezone

import pandas as pd

from udg_catalogue.maps import cluster_label
from udg_catalogue.ui.forum import (
    BoardRow,
    board_html,
    board_rows,
    breadcrumb_html,
    footer_html,
    legend_html,
    mapped_mask,
    nav_html,
    stats_html,
    stats_lines,
    tagline_html,
)

MANIFEST = {
    "llm": {"model": "deepseek-chat"},
    "software": {"sci-etl-core": "0.7.0"},
    "built_at": "2026-10-21T09:30:00+00:00",
}
CATALOGUE = pd.DataFrame(
    {
        "galaxy_name": ["DF2", "DF4", "DF44", "UGC 2162", "X1"],
        "quality_flag": ["Confirmed", "Needs Review", "Confirmed", "Low Confidence", "Needs Review"],
        "constellation": ["Cetus", "Cetus", "Coma Berenices", "Cetus", None],
        "cluster_id": [10, 10, -1, 10, 3],
        "ra": [40.44, 39.81, 195.24, 40.1, None],
        "dec": [-8.40, -8.12, 26.98, 1.23, None],
        "distance_mpc": [17.7, 18.8, 100.0, 12.3, 5.0],
        "effective_radius_kpc": [2.26, 1.66, 4.6, 1.7, None],
        "stellar_mass_solar": [2.2e8, 1.5e8, 3.0e8, None, None],
    }
)


def test_tagline_counts_the_catalogue():
    assert tagline_html(1927) == (
        '<div class="udg-tagline">1,927 galaxies in the catalogue · '
        "ultra-diffuse galaxies extracted from the literature</div>"
    )


def test_nav_links_every_view_but_the_current_one_and_shows_the_time():
    markup = nav_html([("Data Table", "table"), ("Analytics", "analytics")], "Data Table", datetime(2026, 10, 21, 15, 40, tzinfo=timezone.utc))

    assert markup == (
        '<div class="udg-navbar"><span><span class="udg-nav-here">Data Table</span> · '
        '<a href="?view=analytics" target="_self">Analytics</a></span>'
        '<span class="udg-now">It is currently Wed Oct 21, 2026 15:40</span></div>'
    )


def test_breadcrumb_marks_the_last_crumb_and_escapes_text():
    markup = breadcrumb_html(["UDG Catalogue", "Galaxies", "<Table>"])

    assert markup == (
        '<div class="udg-crumbs"><span class="udg-crumb">UDG Catalogue</span>'
        '<span class="udg-crumb-sep">›</span><span class="udg-crumb">Galaxies</span>'
        '<span class="udg-crumb-sep">›</span><span class="udg-crumb udg-crumb-here">&lt;Table&gt;</span></div>'
    )


def test_mapped_mask_needs_a_position_and_a_non_negative_distance():
    frame = CATALOGUE.assign(distance_mpc=[17.7, -1.0, 100.0, 12.3, 5.0])

    assert mapped_mask(frame).tolist() == [True, False, True, True, False]
    assert not mapped_mask(CATALOGUE.drop(columns=["ra"])).any()


def test_board_rows_rank_groups_and_name_the_nearest_mapped_galaxy():
    rows, hidden = board_rows(CATALOGUE, "constellation", limit=2)

    assert rows == [
        BoardRow("Cetus", 3, 1, 3, "UGC 2162 · 12.3 Mpc"),
        BoardRow("Coma Berenices", 1, 1, 1, "DF44 · 100 Mpc"),
    ]
    assert hidden == 1
    unknown = board_rows(CATALOGUE, "constellation")[0][-1]
    assert unknown == BoardRow("Unknown", 1, 0, 0, "—")

    clusters, _hidden = board_rows(CATALOGUE.drop(columns=["quality_flag"]), "cluster_id", cluster_label)
    assert [row.name for row in clusters] == ["Cluster #10", "Cluster #3", "Single / Unclustered"]
    assert all(row.confirmed == 0 for row in clusters)

    assert board_rows(CATALOGUE.iloc[0:0], "constellation") == ([], 0)
    assert board_rows(CATALOGUE, "missing") == ([], 0)


def test_board_html_draws_lamps_counts_and_the_hidden_row():
    rows = [BoardRow("Cetus", 1234, 2, 3, "DF2 · 17.7 Mpc"), BoardRow("<Leo>", 1, 0, 0)]

    markup = board_html("Constellation", rows, 4, "constellations")

    assert markup.startswith('<table class="udg-forumline"><thead><tr><th class="udg-lamp"></th><th>Constellation</th>')
    assert '<td class="udg-lamp" title="has confirmed galaxies">■</td><td class="udg-board-name">Cetus</td>' in markup
    assert '<td class="udg-num">1,234</td>' in markup
    assert '<td class="udg-lamp" title="no confirmed galaxy yet">□</td><td class="udg-board-name">&lt;Leo&gt;</td>' in markup
    assert '<tr class="udg-more"><td></td><td colspan="5">... 4 more constellations</td></tr>' in markup
    assert "udg-more" not in board_html("Cluster", rows, 0, "clusters")


def test_stats_lines_name_sizes_flags_mapping_records_and_the_last_build():
    assert stats_lines(CATALOGUE, CATALOGUE.iloc[:3], MANIFEST) == [
        "The catalogue holds 5 galaxies in 2 constellations and 2 clusters; the current selection shows 3.",
        "Confirmed 2 · Needs Review 1",
        "With a position and a distance: 3 · median distance 18.8 Mpc",
        "Largest: DF44 (4.6 kpc) · Most massive: DF44 (3.00e+08 M☉)",
        "Last build 2026-10-21 · model deepseek-chat · sci-etl-core/0.7.0.",
    ]
    bare = CATALOGUE[["galaxy_name", "constellation", "cluster_id"]]
    assert stats_lines(bare, bare, None) == [
        "The catalogue holds 5 galaxies in 2 constellations and 2 clusters; the current selection shows 5.",
        "With a position and a distance: 0",
        "Last build: no run manifest in this workspace.",
    ]


def test_stats_legend_and_footer_markup():
    assert stats_html(["a < b", "c"]) == (
        '<div class="udg-stats"><div class="udg-stats-row">a &lt; b</div><div class="udg-stats-row">c</div></div>'
    )
    assert "■</span> has confirmed galaxies" in legend_html() and "□</span> no confirmed galaxy yet" in legend_html()
    assert footer_html("1.0.0", "0.7.0") == '<div class="udg-footer">UDG Catalogue 1.0.0 · powered by sci-etl-core 0.7.0</div>'
