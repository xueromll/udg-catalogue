from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd
import streamlit as st
from sci_etl_core import SearchQueryError
from sci_etl_core.discovery import DiscoveryResult, Facet
from sci_etl_core.embeddings import AsyncEmbedder
from sci_etl_core.search import DiscoveryGraph, SearchDocument, filter_graph

from udg_catalogue import __version__
from udg_catalogue.config import (
    DEFAULT_CONFIG_PATH,
    EMBEDDING_API_KEY_ENV_VAR,
    KEY_COLUMN,
    CatalogueConfig,
    embedding_key_missing,
    load_catalogue_config,
)
from udg_catalogue.literature import (
    LibraryOverview,
    PaperLibrary,
    PaperLibraryService,
    build_embedder,
    galaxy_query,
    open_paper_library,
    paper_filters,
)
from udg_catalogue.logs import configure_run_logging
from udg_catalogue.maps import build_3d_figure, cluster_label, prepare_map_frame
from udg_catalogue.paper_views import highlight_markdown
from udg_catalogue.postprocess import build_sorted_catalogue, read_catalogue
from udg_catalogue.ui import charts
from udg_catalogue.ui.chips import (
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
from udg_catalogue.ui.facets import facet_groups, overview_facets, selection_filters, toggled
from udg_catalogue.ui.forum import (
    SITE_NAME,
    board_html,
    board_rows,
    breadcrumb_html,
    footer_html,
    legend_html,
    nav_html,
    stats_html,
    stats_lines,
    tagline_html,
)
from udg_catalogue.ui.graph import (
    CanvasStyle,
    build_canvas,
    canvas_caption,
    edge_kinds,
    kind_label,
    node_label,
    node_options,
    selected_from_state,
)
from udg_catalogue.ui.hits import hit_html
from udg_catalogue.ui.inspector import (
    NO_MANIFEST,
    NO_REVIEW_STORE,
    card_html,
    extraction_stamp,
    find_paper,
    galaxies_from_paper,
    load_manifest,
    paper_card,
    rejections_for,
    stamp_html,
)
from udg_catalogue.ui.theme import style_tag

ALL = "All"
CONFIG_ENV_VAR = "UDG_CATALOGUE_CONFIG"
READ_ONLY_ENV_VAR = "UDG_DASHBOARD_READ_ONLY"
TABLE_VIEW = "Data Table"
ANALYTICS_VIEW = "Analytics"
PAPERS_VIEW = "Paper Search"
VIEWS: tuple[str, ...] = (TABLE_VIEW, ANALYTICS_VIEW, PAPERS_VIEW)
VIEW_SLUGS: dict[str, str] = {"table": TABLE_VIEW, "analytics": ANALYTICS_VIEW, "papers": PAPERS_VIEW}
VIEW_SECTIONS: dict[str, str] = {TABLE_VIEW: "Galaxies", ANALYTICS_VIEW: "Galaxies", PAPERS_VIEW: "Papers"}
VIEW_PARAM = "view"
QUERY_PARAM = "q"
PAPER_PARAM = "paper"
QUERY_KEY = "query-bar"
HEADER_KEY = "site-header"
GALAXY_KEY = "galaxy-pick"
SEED_KEY = "graph_seed"
SELECTED_KEY = "inspector_record"
FACETS_KEY = "facet_selection"
HANDLED_KEY = "graph_handled"
NODE_PICK_KEY = "graph-node"
FULLSCREEN_KEY = "graph-fullscreen"
SEARCH_RESULTS = 20
SEARCH_MODES = {"Hybrid": "hybrid", "Keyword": "lexical", "Meaning": "semantic"}
QUERY_HELP = (
    'Terms, "phrases", prefix* terms, title: or abstract: scopes, AND, OR, NOT or -term, '
    "and NEAR(a b, 5)."
)
QUERY_PLACEHOLDER = '"Malin 1" surface brightness -lensing'
NO_INDEX = (
    "The paper index is empty, so there is nothing to search: run `python main.py --index-papers` "
    "to index the screened papers. The catalogue pages work without it."
)
NO_CATALOGUE = (
    "No catalogue in this workspace. Run `python main.py` to build data/udg_database_sorted.csv, "
    "or restore the committed file."
)
NO_SEARCH = "No search yet. Facets on the left count the whole index until you search."
NO_GRAPH = "Select a hit to grow its graph."
NO_SELECTION = "Select a hit or a node."
NO_HITS = "No paper matches this search."
NO_REJECTIONS = "No rejected extraction for this paper."
PAGE_SIZES = [10, 50, 100]
T = TypeVar("T")
COLOR_OPTIONS = {
    "Dark Matter Fraction": "dark_matter_fraction",
    "Completeness (%)": "completeness_pct",
    "Distance (Mpc)": "distance_mpc",
    "Cluster ID": "cluster_id",
}
PLOTLY_CONFIG = {"displayModeBar": False, "scrollZoom": True}


@st.cache_data
def load_catalogue(path: str, modified_at: float) -> pd.DataFrame:
    return read_catalogue(Path(path))


@st.cache_data
def filter_catalogue(
    catalogue: pd.DataFrame,
    constellation: str,
    cluster: str | int,
    min_completeness: float,
    flag: str,
) -> pd.DataFrame:
    filtered = catalogue
    if constellation != ALL:
        filtered = filtered[filtered["constellation"] == constellation]
    if cluster != ALL:
        filtered = filtered[filtered["cluster_id"] == cluster]
    filtered = filtered[filtered["completeness_pct"] >= min_completeness]
    if flag != ALL:
        filtered = filtered[filtered["quality_flag"] == flag]
    return filtered


def index_version(config: CatalogueConfig) -> tuple[str, float] | None:
    path = config.paths.search_index
    return (str(path), path.stat().st_mtime) if path.is_file() else None


@st.cache_resource(show_spinner="Loading the embedding model...")
def local_embedder(_config: CatalogueConfig, model_name: str) -> AsyncEmbedder:
    return build_embedder(_config.embeddings)


def shared_embedder(config: CatalogueConfig) -> AsyncEmbedder | None:
    if config.embeddings.enabled and config.embeddings.provider == "local":
        return local_embedder(config, config.embeddings.model)
    return None


@st.cache_resource(show_spinner="Opening the paper library...")
def paper_service(_config: CatalogueConfig, settings: str) -> PaperLibraryService:
    return PaperLibraryService(lambda: open_paper_library(_config, shared_embedder(_config)))


def on_library(
    config: CatalogueConfig, version: tuple[str, float], operation: Callable[[PaperLibrary], Awaitable[T]]
) -> T:
    return paper_service(config, config.model_dump_json()).run(operation, version)


@st.cache_data
def paper_overview(_config: CatalogueConfig, version: tuple[str, float]) -> LibraryOverview:
    return on_library(_config, version, lambda library: library.overview())


@st.cache_data(show_spinner="Searching papers...")
def search_papers(
    _config: CatalogueConfig,
    version: tuple[str, float],
    query: str,
    mode: str,
    categories: tuple[str, ...],
    years: tuple[int, int] | None,
) -> DiscoveryResult:
    filters = paper_filters(categories, years)
    return on_library(
        _config,
        version,
        lambda library: library.search(query, mode=mode, filters=filters, top_k=SEARCH_RESULTS),
    )


@st.cache_data(show_spinner="Growing the discovery graph...")
def related_papers(_config: CatalogueConfig, version: tuple[str, float], record_id: str) -> DiscoveryGraph:
    return on_library(_config, version, lambda library: library.related_papers(record_id))


@st.cache_data
def paper_document(_config: CatalogueConfig, version: tuple[str, float], record_id: str) -> SearchDocument | None:
    documents = on_library(_config, version, lambda library: library.documents([record_id]))
    return documents.get(record_id)


def filtered_graph(
    graph: DiscoveryGraph, categories: tuple[str, ...], years: tuple[int, int] | None
) -> DiscoveryGraph:
    filters = paper_filters(categories, years)
    return filter_graph(graph, filters=filters) if filters else graph


def current_catalogue(config: CatalogueConfig) -> pd.DataFrame:
    path = config.paths.sorted_catalogue
    if not path.is_file():
        return pd.DataFrame()
    return load_catalogue(str(path), path.stat().st_mtime)


def refresh_catalogue(config: CatalogueConfig) -> None:
    with st.spinner("Processing data..."):
        try:
            log = configure_run_logging(config.paths.log_file)
            rebuilt = build_sorted_catalogue(config, log.info)
        except Exception as error:
            st.sidebar.error(f"Error updating data: {error}")
            return
    if rebuilt is None:
        st.sidebar.error("Raw catalogue not found. Run the pipeline first.")
        return
    st.cache_data.clear()
    st.rerun()


def html(markup: str) -> None:
    """Draw one of the ui package's HTML fragments; nothing is drawn for an empty one."""
    if markup:
        st.markdown(markup, unsafe_allow_html=True)


def select_hit(record_id: str) -> None:
    st.session_state[SELECTED_KEY] = record_id
    st.session_state[SEED_KEY] = record_id


def select_node(record_id: str) -> None:
    st.session_state[SELECTED_KEY] = record_id


def pick_node() -> None:
    record_id = st.session_state.get(NODE_PICK_KEY)
    if record_id:
        select_node(record_id)


def open_in_graph() -> None:
    st.session_state[SEED_KEY] = st.session_state.get(SELECTED_KEY)


def toggle_facet(key: str, value: str) -> None:
    st.session_state[FACETS_KEY] = toggled(st.session_state.get(FACETS_KEY, {}), key, value)


def clear_facets() -> None:
    st.session_state[FACETS_KEY] = {}


def apply_galaxy() -> None:
    galaxy = st.session_state.get(GALAXY_KEY)
    if galaxy:
        st.session_state[QUERY_KEY] = galaxy_query(galaxy)


def sidebar_filters(catalogue: pd.DataFrame) -> tuple[str, str | int, float, str]:
    constellations = [ALL, *sorted(catalogue["constellation"].dropna().unique().tolist())]
    clusters = [ALL, *sorted(catalogue["cluster_id"].dropna().astype(int).unique().tolist())]
    constellation = st.selectbox("Constellation", constellations)
    cluster = st.selectbox("Cluster ID", clusters)
    min_completeness = st.slider("Minimum Completeness (%)", 0.0, 100.0, 0.0, 10.0)
    flag = ALL
    if "quality_flag" in catalogue.columns:
        flags = [ALL, *sorted(catalogue["quality_flag"].dropna().unique().tolist())]
        flag = st.selectbox("Quality Flag", flags)
    return constellation, cluster, min_completeness, flag


def render_map(filtered: pd.DataFrame) -> None:
    with st.expander("3D galaxy distribution", expanded=True):
        color_label = st.selectbox("Select color mapping parameter:", list(COLOR_OPTIONS))
        map_frame = prepare_map_frame(filtered)
        if map_frame.empty:
            html(quiet_html("No galaxy in the selection has a position and a distance to map."))
            return
        color_column = COLOR_OPTIONS[color_label]
        color_range = None
        if color_column == "cluster_id":
            map_frame["cluster_label"] = map_frame["cluster_id"].map(cluster_label)
            color_column = "cluster_label"
        elif color_column == "dark_matter_fraction":
            color_range = (0.0, 1.0)
        elif color_column == "distance_mpc":
            color_range = (map_frame["distance_mpc"].min(), map_frame["distance_mpc"].quantile(0.99))
        figure = build_3d_figure(map_frame, color_column=color_column, color_label=color_label, color_range=color_range)
        html(status_html(f"{len(map_frame):,} galaxies with a position and a distance · colour {color_label}"))
        st.plotly_chart(charts.restyle_map(figure), width="stretch", theme=None, config=PLOTLY_CONFIG)


def render_table(filtered: pd.DataFrame) -> None:
    with st.container(key="board-table"):
        draw_table(filtered)


def draw_table(filtered: pd.DataFrame) -> None:
    st.subheader("Data Table")
    if "current_page" not in st.session_state:
        st.session_state.current_page = 1

    def reset_page() -> None:
        st.session_state.current_page = 1

    def previous_page() -> None:
        st.session_state.current_page -= 1

    def next_page() -> None:
        st.session_state.current_page += 1

    size_column, info_column, previous_column, next_column = st.columns([1, 2, 1, 1])
    with size_column:
        page_size = st.selectbox("Objects per page:", options=PAGE_SIZES, index=0, on_change=reset_page)
    total_pages = max(1, (len(filtered) - 1) // page_size + 1)
    st.session_state.current_page = min(st.session_state.current_page, total_pages)
    with info_column:
        html(
            "<div class='udg-status' style='text-align: center; margin-top: 32px;'>"
            f"page {st.session_state.current_page} of {total_pages}</div>"
        )
    with previous_column:
        html("<div style='margin-top: 28px;'></div>")
        st.button("Previous", on_click=previous_page, disabled=st.session_state.current_page == 1, width="stretch")
    with next_column:
        html("<div style='margin-top: 28px;'></div>")
        st.button("Next", on_click=next_page, disabled=st.session_state.current_page == total_pages, width="stretch")
    start = (st.session_state.current_page - 1) * page_size
    st.dataframe(filtered.iloc[start : start + page_size], width="stretch", hide_index=True)


def render_figure(figure: Any, empty_message: str) -> None:
    if figure is None:
        html(quiet_html(empty_message))
    else:
        st.plotly_chart(figure, width="stretch", theme=None, config=PLOTLY_CONFIG)


def render_analytics(filtered: pd.DataFrame) -> None:
    with st.container(key="board-analytics"):
        st.subheader("Statistical Analytics")
        mass_column, radius_column = st.columns(2)
        with mass_column:
            render_figure(charts.stellar_mass_histogram(filtered), "Not enough data to plot the stellar mass.")
        with radius_column:
            render_figure(charts.effective_radius_histogram(filtered), "Not enough data to plot the effective radius.")
        render_figure(charts.mass_radius_scatter(filtered), "Not enough data for the mass against radius plot.")


def render_index(filtered: pd.DataFrame) -> None:
    constellations, clusters = st.columns(2)
    with constellations:
        html(board_html("Constellation", *board_rows(filtered, "constellation"), "constellations"))
    with clusters:
        html(board_html("Cluster", *board_rows(filtered, "cluster_id", cluster_label), "clusters"))


def render_stats(config: CatalogueConfig, catalogue: pd.DataFrame, filtered: pd.DataFrame) -> None:
    with st.container(key="board-stats"):
        html(region_html("Statistics"))
        html(stats_html(stats_lines(catalogue, filtered, load_manifest(config.paths.run_manifest))))
        html(legend_html())
    html(footer_html(__version__, version("sci-etl-core")))


def render_facets(area: Any, facets: Sequence[Facet], selection: dict[str, tuple[str, ...]]) -> None:
    with area, st.container(key="block-facets"):
        html(region_html("Facets"))
        for group in facet_groups(facets, selection):
            html(f'<div class="udg-meta">{group.key}</div>')
            for row in group.rows:
                st.button(
                    f"{row.value} · {row.count:,}",
                    key=row.widget_key,
                    type="tertiary",
                    on_click=toggle_facet,
                    args=(row.key, row.value),
                )
            if group.hidden:
                html(quiet_html(f"... {group.hidden} more"))
        if selection:
            st.button("Clear filters", key="facet-clear", on_click=clear_facets)


def render_hits(result: DiscoveryResult, selected: str | None) -> None:
    html(region_html(f"Hits  {len(result.hits)} of {result.total_matched:,}"))
    if not result.hits:
        html(quiet_html(NO_HITS))
    for position, hit in enumerate(result.hits, start=1):
        with st.container(key=f"topic-{hit.record_id}"):
            html(hit_html(position, hit, selected))
            for snippet in hit.snippets:
                st.markdown(f"{snippet.field}: {highlight_markdown(snippet)}")
            st.button("Select", key=f"hit-{hit.record_id}", type="tertiary", on_click=select_hit, args=(hit.record_id,))


def render_graph(graph: DiscoveryGraph, result: DiscoveryResult | None, fullscreen: bool) -> str | None:
    """Draw the canvas and its controls, apply a click on a node, and return the selected record."""
    html(region_html("Graph"))
    kinds = edge_kinds(graph)
    kinds_on: set[str] = set()
    for column, kind in zip(st.columns(max(len(kinds), 1)), kinds, strict=False):
        with column:
            if st.checkbox(kind_label(kind), value=True, key=f"edge-kind-{kind}"):
                kinds_on.add(kind)
    hit_ids = frozenset(hit.record_id for hit in result.hits) if result is not None else frozenset()
    style = CanvasStyle(hit_ids, st.session_state.get(SELECTED_KEY), frozenset(kinds_on), fullscreen)
    state = st.plotly_chart(
        build_canvas(graph, style),
        key="graph-canvas",
        on_select="rerun",
        selection_mode="points",
        theme=None,
        config=PLOTLY_CONFIG,
    )
    clicked = selected_from_state(state)
    if clicked and clicked != st.session_state.get(HANDLED_KEY):
        st.session_state[HANDLED_KEY] = clicked
        select_node(clicked)
    html(status_html(canvas_caption(graph, style)))
    st.selectbox(
        "Select a node",
        ["", *node_options(graph)],
        key=NODE_PICK_KEY,
        format_func=lambda record_id: node_label(graph, record_id) if record_id else "",
        on_change=pick_node,
    )
    return st.session_state.get(SELECTED_KEY)


def render_inspector(
    config: CatalogueConfig,
    version: tuple[str, float],
    catalogue: pd.DataFrame,
    result: DiscoveryResult | None,
    graph: DiscoveryGraph | None,
    selected: str | None,
) -> None:
    html(region_html("Inspector"))
    if not selected:
        html(quiet_html(NO_SELECTION))
        return
    card = find_paper(result, graph, selected)
    if card is None:
        document = paper_document(config, version, selected)
        card = paper_card(selected, "", {}) if document is None else paper_card(selected, document.title, document.metadata)
    html(card_html(card))
    st.button(
        "Open in graph",
        key="open-in-graph",
        type="primary",
        on_click=open_in_graph,
        disabled=st.session_state.get(SEED_KEY) == selected,
    )
    html(region_html("Galaxies from this paper"))
    rows, note = galaxies_from_paper(catalogue, selected)
    if note:
        html(quiet_html(note))
    else:
        st.dataframe(rows, width="stretch", hide_index=True)
    html(region_html("Rejected extractions"))
    rejected = rejections_for(config.paths.rejections, selected)
    if rejected is None:
        html(quiet_html(NO_REVIEW_STORE))
    elif not rejected:
        html(quiet_html(NO_REJECTIONS))
    else:
        st.dataframe(pd.DataFrame(rejected), width="stretch", hide_index=True)
    html(region_html("Extraction stamp"))
    manifest = load_manifest(config.paths.run_manifest)
    html(quiet_html(NO_MANIFEST) if manifest is None else stamp_html(extraction_stamp(manifest)))


def render_papers(config: CatalogueConfig, catalogue: pd.DataFrame, galaxies: pd.DataFrame, facet_area: Any) -> None:
    version = index_version(config)
    if version is None:
        html(quiet_html(NO_INDEX))
        return
    if embedding_key_missing(config):
        st.error(f"Set {EMBEDDING_API_KEY_ENV_VAR} to search papers with the openai embeddings provider.")
        return
    overview = paper_overview(config, version)
    names = sorted(galaxies[KEY_COLUMN].dropna().astype(str).unique().tolist())
    query_column, mode_column, galaxy_column = st.columns([6, 2, 3])
    with query_column:
        query = st.text_input("Search papers", key=QUERY_KEY, help=QUERY_HELP, placeholder=QUERY_PLACEHOLDER)
    with mode_column:
        modes = SEARCH_MODES if config.embeddings.enabled else {"Keyword": "lexical"}
        mode = modes[st.selectbox("Match by", list(modes))]
    with galaxy_column:
        st.selectbox("Papers mentioning a galaxy", ["", *names], key=GALAXY_KEY, on_change=apply_galaxy)

    selection = st.session_state.get(FACETS_KEY, {})
    categories, years = selection_filters(selection)
    result = None
    if query.strip():
        try:
            result = search_papers(config, version, query, mode, categories, years)
        except SearchQueryError as error:
            st.error(f"{error} (column {error.position})")
    chips = [*(query_chips(result.chips) if result is not None else []), *filter_chips(categories, years)]
    html(chips_html(chips))
    if result is None:
        html(status_html(f"{overview.papers:,} papers indexed"))
    else:
        html(status_html(status_line(result, mode)))
    seed = st.session_state.get(SEED_KEY)
    graph = filtered_graph(related_papers(config, version, seed), categories, years) if seed else None
    html(banner_html(banner_lines(result, graph)))
    render_facets(facet_area, overview_facets(overview.categories) if result is None else result.facets, selection)

    fullscreen = st.toggle("Graph fullscreen", key=FULLSCREEN_KEY)
    if fullscreen:
        graph_area = st.container()
        hits_column, inspector_column = st.columns([1, 1])
    else:
        hits_column, graph_area, inspector_column = st.columns([3, 5, 3])
    with graph_area:
        if graph is None:
            html(region_html("Graph"))
            html(quiet_html(NO_GRAPH))
            selected = st.session_state.get(SELECTED_KEY)
        else:
            selected = render_graph(graph, result, fullscreen)
    with hits_column:
        if result is None:
            html(region_html("Hits"))
            html(quiet_html(NO_SEARCH))
        else:
            render_hits(result, selected)
    with inspector_column:
        render_inspector(config, version, catalogue, result, graph, selected)


def main() -> None:
    st.set_page_config(page_title="UDG catalogue", layout="wide")
    st.html(style_tag())
    config = load_catalogue_config(Path(os.environ.get(CONFIG_ENV_VAR, DEFAULT_CONFIG_PATH)))
    catalogue = current_catalogue(config)
    if QUERY_KEY not in st.session_state:
        st.session_state[QUERY_KEY] = st.query_params.get(QUERY_PARAM, "")
        if st.query_params.get(PAPER_PARAM):
            select_hit(st.query_params[PAPER_PARAM])

    header = st.container(key=HEADER_KEY)
    with header:
        st.title("Ultra-Diffuse Galaxies (UDG) Research Dashboard")
        if not catalogue.empty:
            html(tagline_html(len(catalogue)))
    if catalogue.empty:
        html(quiet_html(NO_CATALOGUE))
        return

    with st.sidebar.container(key="block-navigation"):
        html(region_html("Navigation"))
        if os.environ.get(READ_ONLY_ENV_VAR) != "1" and st.button("Refresh Data", width="stretch"):
            refresh_catalogue(config)
        view_mode = st.radio(
            "View",
            options=VIEWS,
            index=VIEWS.index(VIEW_SLUGS.get(st.query_params.get(VIEW_PARAM, ""), TABLE_VIEW)),
            help="The galaxy table, the statistical plots, or a search over the screened papers",
        )
    facet_area = st.sidebar.container()
    with st.sidebar.container(key="block-filters"):
        html(region_html("Catalogue filters"))
        filtered = filter_catalogue(catalogue, *sidebar_filters(catalogue))
        html(status_html(f"{len(filtered):,} of {len(catalogue):,} galaxies"))
        st.download_button(
            label="Download filtered CSV",
            data=filtered.to_csv(index=False).encode("utf-8"),
            file_name="filtered_udg_database.csv",
            mime="text/csv",
            width="stretch",
        )

    with header:
        html(nav_html([(label, slug) for slug, label in VIEW_SLUGS.items()], view_mode, datetime.now().astimezone()))
    html(breadcrumb_html([SITE_NAME, VIEW_SECTIONS[view_mode], view_mode]))
    if view_mode == PAPERS_VIEW:
        render_papers(config, catalogue, filtered, facet_area)
    else:
        if not filtered.empty:
            render_index(filtered)
        render_map(filtered)
        if filtered.empty:
            html(quiet_html("No galaxy matches the catalogue filters. Widen them in the sidebar."))
        elif view_mode == TABLE_VIEW:
            render_table(filtered)
        else:
            render_analytics(filtered)
    render_stats(config, catalogue, filtered)

main()
