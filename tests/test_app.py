import asyncio
import json
from pathlib import Path

import pytest
from sci_etl_core.search import AsyncSqliteFts5Store, SearchDocument
from streamlit.testing.v1 import AppTest

from udg_catalogue.config import PAPER_FACET_KEYS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = PROJECT_ROOT / "app.py"
COMMITTED_CATALOGUE = PROJECT_ROOT / "udg_database_sorted.csv"
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


def color_selector(app):
    return next(selectbox for selectbox in app.selectbox if selectbox.label == COLOR_SELECTOR)


def labelled(widgets, label):
    return next(widget for widget in widgets if widget.label == label)


def write_index(path):
    async def fill():
        store = AsyncSqliteFts5Store(path, facet_keys=PAPER_FACET_KEYS)
        try:
            await store.index(INDEXED_PAPERS)
        finally:
            await store.aclose()

    asyncio.run(fill())


@pytest.fixture
def paper_project(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"paths:\n  sorted_catalogue: {json.dumps(str(COMMITTED_CATALOGUE))}\nembeddings:\n  enabled: false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_ENV_VAR, str(config_path))
    return tmp_path


def open_paper_search(app):
    app.run()
    app.sidebar.radio[0].set_value(PAPERS_VIEW).run()
    assert not app.exception
    return app


def test_dashboard_renders_every_view_of_the_committed_catalogue():
    app = AppTest.from_file(str(APP_PATH), default_timeout=120).run()

    assert not app.exception
    assert app.title[0].value == "Ultra-Diffuse Galaxies (UDG) Research Dashboard"
    assert len(app.dataframe) == 1

    for option in ("Cluster ID", "Distance (Mpc)", "Completeness (%)"):
        color_selector(app).set_value(option).run()
        assert not app.exception

    app.sidebar.radio[0].set_value("Analytics").run()
    assert not app.exception
    assert app.subheader[-1].value == "Statistical Analytics"


def test_paper_search_explains_how_to_build_a_missing_index(paper_project):
    app = open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120))

    assert app.subheader[-1].value == "Paper Search"
    assert "python main.py --index-papers" in app.info[0].value


def test_paper_search_finds_papers_and_grows_their_discovery_graph(paper_project):
    write_index(paper_project / "paper_index.db")
    app = open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120))

    assert labelled(app.radio, "Match by").options == ["Keyword"]
    labelled(app.text_input, "Search papers").input('"dark matter"').run()

    assert not app.exception
    rendered = "\n".join(markdown.value for markdown in app.markdown)
    assert "A galaxy lacking dark matter" in rendered
    assert "**dark matter**" in rendered
    assert "keyword #1" in rendered

    app.button(key="related-1606.06291").click().run()

    assert not app.exception
    assert app.subheader[-1].value == "Related Papers"
    assert "1803.10237" in app.dataframe[-1].value["arxiv"].iloc[1]


def test_paper_search_looks_up_papers_mentioning_a_galaxy(paper_project):
    write_index(paper_project / "paper_index.db")
    app = open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120))

    labelled(app.selectbox, "Papers mentioning a galaxy").set_value("N1052-DF2").run()

    assert not app.exception
    assert labelled(app.text_input, "Search papers").value == '"N1052-DF2"'
    rendered = "\n".join(markdown.value for markdown in app.markdown)
    assert "A galaxy lacking dark matter" in rendered
    assert "Dragonfly 44" not in rendered


def test_paper_search_asks_for_the_embedding_key_of_a_remote_provider(paper_project):
    write_index(paper_project / "paper_index.db")
    (paper_project / "config.yaml").write_text(
        f"paths:\n  sorted_catalogue: {json.dumps(str(COMMITTED_CATALOGUE))}\nembeddings:\n  provider: openai\n",
        encoding="utf-8",
    )
    app = open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120))

    assert "EMBEDDING_API_KEY" in app.error[0].value


def test_paper_search_reports_malformed_queries(paper_project):
    write_index(paper_project / "paper_index.db")
    app = open_paper_search(AppTest.from_file(str(APP_PATH), default_timeout=120))

    labelled(app.text_input, "Search papers").input("(dark OR").run()

    assert not app.exception
    assert "column" in app.error[0].value
