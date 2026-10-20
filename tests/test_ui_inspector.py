import asyncio
import json

import pandas as pd
from sci_etl_core.claims import AsyncSqliteRejectionStore, ExtractionStamp, RejectedEntity, rejection_id
from sci_etl_core.discovery import DiscoveryResult
from sci_etl_core.processors import Violation
from sci_etl_core.search import DiscoveryGraph, FusedHit, GraphNode

from udg_catalogue.ui.inspector import (
    NO_GALAXIES,
    NO_SOURCE_COLUMN,
    PaperCard,
    bare_id,
    card_html,
    extraction_stamp,
    find_paper,
    galaxies_from_paper,
    load_manifest,
    paper_card,
    paper_ids,
    rejection_row,
    rejections_for,
    stamp_html,
)

METADATA = {"categories": ["astro-ph.GA"], "year": "2018", "authors": ["A", "B"]}
RESULT = DiscoveryResult("q", (), (FusedHit("1803.10237", 1.0, title="A galaxy", metadata=METADATA),), None, (), 1, 1.0)
GRAPH = DiscoveryGraph((GraphNode("1606.06291", "Dragonfly 44", metadata={"year": "2016"}),), (), "1606.06291", True)


def test_bare_id_drops_the_version_suffix_and_whitespace():
    assert bare_id(" 2301.04512v2 ") == "2301.04512"
    assert bare_id("2301.04512") == "2301.04512"


def test_paper_card_normalises_title_categories_and_authors():
    card = paper_card("x", "  A   title ", {"categories": "astro-ph.GA", "year": "2020", "authors": ["A"]})

    assert card == PaperCard("x", "A title", "2020", ("astro-ph.GA",), "A")
    assert card.url == "https://arxiv.org/abs/x"
    assert paper_card("y", "", {}) == PaperCard("y", "y", "n.d.", (), "")


def test_find_paper_looks_in_the_hits_then_the_graph():
    assert find_paper(RESULT, GRAPH, "1803.10237") == PaperCard("1803.10237", "A galaxy", "2018", ("astro-ph.GA",), "A, B")
    assert find_paper(RESULT, GRAPH, "1606.06291") == PaperCard("1606.06291", "Dragonfly 44", "2016", (), "")
    assert find_paper(RESULT, GRAPH, "missing") is None
    assert find_paper(None, None, "1803.10237") is None


def test_card_html_links_the_id_and_omits_what_is_missing():
    markup = card_html(PaperCard("1803.10237", "A <galaxy>", "2018", ("astro-ph.GA", "astro-ph.CO"), "A, B"))

    assert '<a href="https://arxiv.org/abs/1803.10237">1803.10237</a>' in markup
    assert '<div class="udg-title">A &lt;galaxy&gt;</div><div class="udg-meta">A, B</div>' in markup
    assert "year 2018 · astro-ph.GA, astro-ph.CO" in markup

    bare = card_html(PaperCard("y", "y", "n.d.", (), ""))

    assert "no category" in bare
    assert bare.count("udg-meta") == 1


def test_paper_ids_split_a_source_papers_cell_and_tolerate_missing_values():
    assert paper_ids(None) == set()
    assert paper_ids(float("nan")) == set()
    assert paper_ids("1803.10237v2; 1606.06291;") == {"1803.10237", "1606.06291"}


def test_galaxies_from_paper_match_source_papers_or_record_id_with_the_measured_columns():
    catalogue = pd.DataFrame(
        {
            "galaxy_name": ["DF2", "DF44", "Other"],
            "completeness_pct": [100.0, 50.0, 10.0],
            "source_papers": ["1803.10237; 1606.06291", "1606.06291v3", None],
            "ra": [40.4, 195.2, 1.0],
            "stellar_mass_solar": [2e8, 3e8, 1e7],
        }
    )

    rows, note = galaxies_from_paper(catalogue, "1606.06291v1")

    assert note == ""
    assert list(rows.columns) == ["galaxy_name", "ra", "stellar_mass_solar"]
    assert rows["galaxy_name"].tolist() == ["DF2", "DF44"]
    rows, note = galaxies_from_paper(catalogue, "2401.00001")

    assert (len(rows), note) == (0, NO_GALAXIES)

    raw = pd.DataFrame({"record_id": ["1803.10237", "1606.06291v2"], "galaxy_name": ["DF2", "DF44"]})
    rows, note = galaxies_from_paper(raw, "1606.06291")

    assert (rows["galaxy_name"].tolist(), note) == (["DF44"], "")

    rows, note = galaxies_from_paper(pd.DataFrame({"galaxy_name": ["DF2"]}), "1803.10237")

    assert (len(rows), note) == (0, NO_SOURCE_COLUMN)


def test_rejections_for_reads_the_review_store_and_says_when_there_is_none(tmp_path):
    path = tmp_path / "rejected_galaxies.db"
    assert rejections_for(path, "1803.10237") is None

    stamp = ExtractionStamp(model="deepseek", prompt_hash="p" * 64, schema_hash="s" * 64, extractor_version="sci-etl-core/0.7.0")
    violation = Violation(code="out-of-range", field="effective_radius_kpc", severity="error", message="too large")
    entity = {"galaxy_name": "DF2", "effective_radius_kpc": 900.0}
    entry = RejectedEntity(
        entry_id=rejection_id("1803.10237", entity, [violation], stamp),
        record_id="1803.10237",
        entity=entity,
        violations=(violation,),
        stamp=stamp,
        quote="R_eff = 900 kpc",
        created_at="2026-10-20T10:00:00+00:00",
    )

    async def fill():
        store = AsyncSqliteRejectionStore(path)
        try:
            await store.put([entry])
        finally:
            await store.aclose()

    asyncio.run(fill())

    assert rejections_for(path, "1803.10237") == [
        {
            "galaxy": "DF2",
            "reasons": "effective_radius_kpc out-of-range",
            "quote": "R_eff = 900 kpc",
            "status": "unresolved",
            "rejected_at": "2026-10-20",
        }
    ]
    assert rejections_for(path, "1606.06291") == []

    path.write_text("not a database", encoding="utf-8")
    assert rejections_for(path, "1803.10237") is None


def test_rejection_row_falls_back_to_the_whole_entity_and_names_whole_entity_violations():
    row = rejection_row(json.dumps({"name": "x"}), json.dumps([{"code": "missing-name", "field": None}]), "", "2026-01-02T00:00:00", "kept")

    assert row == {"galaxy": '{"name": "x"}', "reasons": "missing-name", "quote": "", "status": "kept", "rejected_at": "2026-01-02"}


def test_load_manifest_returns_only_a_json_object(tmp_path):
    path = tmp_path / "run_manifest.json"
    assert load_manifest(path) is None

    path.write_text("[1, 2]", encoding="utf-8")
    assert load_manifest(path) is None

    path.write_text("{not json", encoding="utf-8")
    assert load_manifest(path) is None

    path.write_text('{"llm": {"model": "m"}}', encoding="utf-8")
    assert load_manifest(path) == {"llm": {"model": "m"}}


def test_extraction_stamp_rows_and_markup():
    assert extraction_stamp({}) == [
        ("model", "unknown"),
        ("prompt", "unknown"),
        ("relevance", "unknown"),
        ("library", "unknown"),
        ("built", "unknown"),
    ]
    manifest = {
        "built_at": "2026-10-20T10:00:00+00:00",
        "software": {"sci-etl-core": "0.7.0"},
        "llm": {"model": "deepseek-v4-flash"},
        "prompts": {"extraction_sha256": "3f9a1c0e" + "0" * 56, "relevance_sha256": "7bd2e9a4" + "0" * 56},
    }
    rows = extraction_stamp(manifest)

    assert rows == [
        ("model", "deepseek-v4-flash"),
        ("prompt", "3f9a1c0e"),
        ("relevance", "7bd2e9a4"),
        ("library", "sci-etl-core/0.7.0"),
        ("built", "2026-10-20"),
    ]
    assert stamp_html(rows[:1]) == '<div class="udg-kv"><span>model</span><span>deepseek-v4-flash</span></div>'
