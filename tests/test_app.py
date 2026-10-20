import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest
from sci_etl_core.claims import AsyncSqliteRejectionStore, ExtractionStamp, RejectedEntity, rejection_id
from sci_etl_core.processors import Violation
from sci_etl_core.search import AsyncSqliteFts5Store, SearchDocument
from streamlit.testing.v1 import AppTest

from udg_catalogue.config import PAPER_FACET_KEYS
from udg_catalogue.literature import PaperLibrary

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = PROJECT_ROOT / "app.py"
COMMITTED_CATALOGUE = PROJECT_ROOT / "data" / "udg_database_sorted.csv"
CONFIG_ENV_VAR = "UDG_CATALOGUE_CONFIG"
COLOR_SELECTOR = "Select color mapping parameter:"
PAPERS_VIEW = "Paper Search"
SHARED_AUTHORS = ["Pieter van Dokkum", "Shany Danieli", "Roberto Abraham"]
INDEXED_PAPERS = [
    SearchDocument(
        "1803.10237",
        "A galaxy lacking dark matter",
        "The ultra-diffuse galaxy N1052-DF2 has little or no dark matter.",
        "Globular cluster kinematics of N1052-DF2.",
        {"categories": ["astro-ph.GA"], "authors": SHARED_AUTHORS, "year": "2018"},
    ),
    SearchDocument(
        "1606.06291",
        "A high stellar velocity dispersion for Dragonfly 44",
        "Dragonfly 44 is dominated by dark matter.",
        "Keck spectroscopy of Dragonfly 44.",
        {"categories": ["astro-ph.GA"], "authors": SHARED_AUTHORS, "year": "2016"},
    ),
    SearchDocument(
        "2401.00001",
        "Tidal features of dwarf galaxies",
        "Deep photometry in the Fornax cluster.",
        "Shells and streams.",
        {"categories": ["astro-ph.CO"], "authors": ["Carla Other"], "year": "2024"},
    ),
]
SMALL_CATALOGUE = (
    "galaxy_name,completeness_pct,quality_flag,constellation,cluster_id,source_papers,ra,dec,distance_mpc,"
    "effective_radius_kpc,stellar_mass_solar,dark_matter_fraction\n"
    "DF2,100.0,Confirmed,Cetus,10,1803.10237; 1606.06291,40.44,-8.40,17.7,2.26,218776160.0,0.0\n"
    "DF44,80.0,Candidate,Coma Berenices,-1,1606.06291v2,195.24,26.98,100.0,4.6,300000000.0,0.98\n"
)


def color_selector(app):
    return next(selectbox for selectbox in app.selectbox if selectbox.label == COLOR_SELECTOR)


def labelled(widgets, label):
    return next(widget for widget in widgets if widget.label == label)


def rendered_markdown(app):
    return "\n".join(markdown.value for markdown in app.markdown)


def write_index(path):
    async def fill():
        store = AsyncSqliteFts5Store(path, facet_keys=PAPER_FACET_KEYS)
        try:
            await store.index(INDEXED_PAPERS)
        finally:
            await store.aclose()

    asyncio.run(fill())


def write_config(project, catalogue=COMMITTED_CATALOGUE, embeddings="enabled: false"):
    (project / "config.yaml").write_text(
        f"paths:\n  sorted_catalogue: {json.dumps(str(catalogue))}\nembeddings:\n  {embeddings}\n",
        encoding="utf-8",
    )


@pytest.fixture
def paper_project(tmp_path, monkeypatch):
    write_config(tmp_path)
    monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "config.yaml"))
    (tmp_path / "data").mkdir()
    return tmp_path


@pytest.fixture
def indexed_project(paper_project):
    write_index(paper_project / "data" / "paper_index.db")
    return paper_project


def open_paper_search(app):
    app.run()
    app.sidebar.radio[0].set_value(PAPERS_VIEW).run()
    assert not app.exception
    return app


def search(app, query):
    labelled(app.text_input, "Search papers").input(query).run()
    assert not app.exception
    return app


def test_dashboard_renders_every_view_of_the_committed_catalogue():
    app = AppTest.from_file(str(APP_PATH), default_timeout=120).run()

    assert not app.exception
    assert app.title[0].value == "Ultra-Diffuse Galaxies (UDG) Research Dashboard"
    assert len(app.dataframe) == 1
    assert len(app.get("html")) == 1
    assert "1,927 galaxies in the catalogue" in rendered_markdown(app)

    for option in ("Cluster ID", "Distance (Mpc)", "Completeness (%)"):
        color_selector(app).set_value(option).run()
        assert not app.exception
        assert len(app.get("plotly_chart")) == 1

    app.sidebar.radio[0].set_value("Analytics").run()
    assert not app.exception
    assert app.subheader[-1].value == "Statistical Analytics"
    assert len(app.get("plotly_chart")) == 4


def test_dashboard_says_quietly_when_nothing_matches_the_filters_or_no_catalogue_exists(tmp_path, monkeypatch):
    catalogue = tmp_path / "small.csv"
    catalogue.write_text(SMALL_CATALOGUE, encoding="utf-8")
    write_config(tmp_path, catalogue=catalogue)
    monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "config.yaml"))
    app = AppTest.from_file(str(APP_PATH), default_timeout=120).run()
    labelled(app.sidebar.selectbox, "Constellation").set_value("Cetus").run()
    labelled(app.sidebar.selectbox, "Cluster ID").set_value(-1).run()

    assert not app.exception
    assert "No galaxy matches the catalogue filters" in rendered_markdown(app)

    write_config(tmp_path, catalogue=tmp_path / "missing.csv")
    monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "config.yaml"))
    app = AppTest.from_file(str(APP_PATH), default_timeout=120).run()

    assert not app.exception
    assert not app.warning and not app.error
    assert "No catalogue in this workspace" in rendered_markdown(app)


@pytest.mark.parametrize(("read_only", "offered"), [(None, True), ("1", False)])
def test_refresh_data_is_offered_unless_the_dashboard_is_read_only(monkeypatch, read_only, offered):
    if read_only is None:
        monkeypatch.delenv("UDG_DASHBOARD_READ_ONLY", raising=False)
    else:
        monkeypatch.setenv("UDG_DASHBOARD_READ_ONLY", read_only)
    app = AppTest.from_file(str(APP_PATH), default_timeout=120).run()

    assert any(button.label == "Refresh Data" for button in app.button) is offered


def test_paper_search_explains_how_to_build_a_missing_index_and_keeps_the_catalogue_pages(paper_project):
    app = open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120))

    assert "python main.py --index-papers" in rendered_markdown(app)
    assert not app.error and not app.text_input

    app.sidebar.radio[0].set_value("Data Table").run()
    assert len(app.dataframe) == 1


def test_paper_search_shows_the_four_regions_empty_before_a_query(indexed_project):
    app = open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120))

    rendered = rendered_markdown(app)
    assert "3 papers indexed" in rendered
    for text in ("No search yet.", "Select a hit to grow its graph.", "Select a hit or a node.", ">Facets<"):
        assert text in rendered
    assert app.button(key="facet-categories-astro-ph.GA").label == "astro-ph.GA · 2"
    assert labelled(app.selectbox, "Match by").options == ["Keyword"]


def test_paper_search_finds_papers_with_chips_and_a_status_line(indexed_project):
    app = search(open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120)), '"dark matter" -tidal')

    rendered = rendered_markdown(app)
    assert '<span class="udg-chip" title="AND">&quot;dark matter&quot;</span>' in rendered
    assert '<span class="udg-chip udg-chip-negated" title="NOT, AND">tidal</span>' in rendered
    assert "2 matched · 2 shown · " in rendered
    assert ">Hits  2 of 2<" in rendered
    assert "A galaxy lacking dark matter" in rendered
    assert "**dark matter**" in rendered
    assert "1803.10237 · 2018 · L1 S- · " in rendered


def test_selecting_a_hit_grows_the_graph_and_fills_the_inspector(indexed_project):
    app = search(open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120)), '"dark matter"')

    app.button(key="hit-1606.06291").click().run()

    assert not app.exception
    assert len(app.get("plotly_chart")) == 1
    rendered = rendered_markdown(app)
    assert "2 nodes · 1 edges · 0 dimmed · seed 1606.06291" in rendered
    assert '<div class="udg-hit-selected">' in rendered
    assert '<a href="https://arxiv.org/abs/1606.06291">1606.06291</a>' in rendered
    assert "year 2016 · astro-ph.GA" in rendered
    assert "predates the source_papers column" in rendered
    assert "no review store in this workspace" in rendered
    assert "no run manifest in this workspace" in rendered
    assert app.button(key="open-in-graph").disabled

    labelled(app.selectbox, "Select a node").set_value("1803.10237").run()

    assert not app.exception
    assert "A galaxy lacking dark matter</div>" in rendered_markdown(app)
    assert not app.button(key="open-in-graph").disabled

    app.button(key="open-in-graph").click().run()

    assert "seed 1803.10237" in rendered_markdown(app)

    labelled(app.checkbox, "metadata (authors, categories)").set_value(False).run()

    assert "2 nodes · 0 edges" in rendered_markdown(app)

    app.toggle[0].set_value(True).run()

    assert not app.exception
    assert len(app.get("plotly_chart")) == 1


def test_inspector_lists_galaxies_rejections_and_the_extraction_stamp_when_the_workspace_has_them(indexed_project):
    catalogue = indexed_project / "small.csv"
    catalogue.write_text(SMALL_CATALOGUE, encoding="utf-8")
    write_config(indexed_project, catalogue=catalogue)
    (indexed_project / "data" / "run_manifest.json").write_text(
        json.dumps(
            {
                "built_at": "2026-10-20T10:00:00+00:00",
                "software": {"sci-etl-core": "0.7.0"},
                "llm": {"model": "deepseek-v4-flash"},
                "prompts": {"extraction_sha256": "3f9a1c0e" * 8, "relevance_sha256": "7bd2e9a4" * 8},
            }
        ),
        encoding="utf-8",
    )
    stamp = ExtractionStamp(model="deepseek-v4-flash", prompt_hash="p" * 64, schema_hash="s" * 64, extractor_version="x")
    violation = Violation(code="out-of-range", field="effective_radius_kpc", severity="error", message="too large")
    entity = {"galaxy_name": "Giant", "effective_radius_kpc": 900.0}
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
        store = AsyncSqliteRejectionStore(indexed_project / "data" / "rejected_galaxies.db")
        try:
            await store.put([entry])
        finally:
            await store.aclose()

    asyncio.run(fill())
    app = search(open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120)), '"dark matter"')

    app.button(key="hit-1803.10237").click().run()

    assert not app.exception
    galaxies, rejections = app.dataframe[-2].value, app.dataframe[-1].value
    assert galaxies["galaxy_name"].tolist() == ["DF2"]
    assert list(galaxies.columns)[:3] == ["galaxy_name", "ra", "dec"]
    assert rejections["galaxy"].tolist() == ["Giant"]
    assert rejections["reasons"].tolist() == ["effective_radius_kpc out-of-range"]
    rendered = rendered_markdown(app)
    assert "<span>model</span><span>deepseek-v4-flash</span>" in rendered
    assert "<span>library</span><span>sci-etl-core/0.7.0</span>" in rendered

    app.button(key="hit-1606.06291").click().run()

    assert len(app.dataframe) == 1
    assert app.dataframe[0].value["galaxy_name"].tolist() == ["DF2", "DF44"]
    assert "No rejected extraction for this paper." in rendered_markdown(app)


def test_selecting_a_facet_requeries_and_shows_a_dashed_chip(indexed_project):
    app = search(open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120)), '"dark matter"')

    app.button(key="facet-year-2016").click().run()

    assert not app.exception
    rendered = rendered_markdown(app)
    assert '<span class="udg-chip udg-chip-filter" title="year">year:2016</span>' in rendered
    assert "1 matched · 1 shown" in rendered
    assert "A galaxy lacking dark matter" not in rendered
    assert app.button(key="facet-on-year-2016").label == "2016 · 1"

    app.button(key="facet-categories-astro-ph.GA").click().run()
    assert '<span class="udg-chip udg-chip-filter" title="categories">categories:astro-ph.GA</span>' in rendered_markdown(app)

    app.button(key="facet-clear").click().run()

    assert "udg-chip-filter" not in rendered_markdown(app)
    assert "2 matched · 2 shown" in rendered_markdown(app)


def test_paper_search_looks_up_papers_mentioning_a_galaxy(indexed_project):
    app = open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120))

    labelled(app.selectbox, "Papers mentioning a galaxy").set_value("N1052-DF2").run()

    assert not app.exception
    assert labelled(app.text_input, "Search papers").value == '"N1052-DF2"'
    rendered = rendered_markdown(app)
    assert "A galaxy lacking dark matter" in rendered
    assert "Dragonfly 44" not in rendered


def test_paper_search_opens_from_query_parameters(indexed_project):
    app = AppTest.from_file(str(APP_PATH), default_timeout=120)
    app.query_params["view"] = "papers"
    app.query_params["q"] = '"dark matter"'
    app.query_params["paper"] = "1606.06291"
    app.run()

    assert not app.exception
    assert app.sidebar.radio[0].value == PAPERS_VIEW
    rendered = rendered_markdown(app)
    assert "A galaxy lacking dark matter" in rendered
    assert "seed 1606.06291" in rendered
    assert "year 2016 · astro-ph.GA" in rendered


def test_paper_search_keeps_a_persistent_banner_for_degraded_and_skipped_legs(indexed_project, monkeypatch):
    original = PaperLibrary.search

    async def weakened(self, query, **kwargs):
        result = await original(self, query, **kwargs)
        return replace(result, degraded=("semantic",), skipped=("citation",))

    monkeypatch.setattr(PaperLibrary, "search", weakened)
    app = search(open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120)), "dark")

    rendered = rendered_markdown(app)
    assert '<div class="udg-banner">' in rendered
    assert "semantic leg failed" in rendered
    assert "citation leg skipped" in rendered
    assert not app.warning and not app.toast


def test_paper_search_asks_for_the_embedding_key_of_a_remote_provider(indexed_project):
    write_config(indexed_project, embeddings="provider: openai")
    app = open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120))

    assert "EMBEDDING_API_KEY" in app.error[0].value


def test_paper_search_reports_malformed_queries(indexed_project):
    app = open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120))

    labelled(app.text_input, "Search papers").input("(dark OR").run()

    assert not app.exception
    assert "column" in app.error[0].value
