from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from sci_etl_core import SearchQueryError, configure_logging
from sci_etl_core.discovery import DiscoveryResult
from sci_etl_core.embeddings import AsyncEmbedder
from sci_etl_core.search import DiscoveryGraph

from udg_catalogue.analytics import effective_radius_histogram, mass_radius_scatter, stellar_mass_histogram
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
    build_embedder,
    galaxy_query,
    paper_filters,
    with_paper_library,
)
from udg_catalogue.maps import build_3d_figure, cluster_label, prepare_map_frame
from udg_catalogue.paper_views import (
    build_graph_figure,
    describe_query,
    escape_markdown,
    graph_table,
    highlight_markdown,
    match_label,
    paper_url,
    publication_year,
)
from udg_catalogue.postprocess import build_sorted_catalogue, read_catalogue

ALL = "All"
LOGGER_NAME = "UDGPipeline"
CONFIG_ENV_VAR = "UDG_CATALOGUE_CONFIG"
TABLE_VIEW = "Data Table"
ANALYTICS_VIEW = "Analytics"
PAPERS_VIEW = "Paper Search"
SEED_KEY = "graph_seed"
SEARCH_RESULTS = 20
SEARCH_MODES = {"Hybrid": "hybrid", "Keyword": "lexical", "Meaning": "semantic"}
QUERY_HELP = (
    'Terms, "phrases", prefix* terms, title: or abstract: scopes, AND, OR, NOT or -term, '
    "and NEAR(a b, 5)."
)
PAGE_SIZES = [10, 50, 100]
COLOR_OPTIONS = {
    "Dark Matter Fraction": "dark_matter_fraction",
    "Completeness (%)": "completeness_pct",
    "Distance (Mpc)": "distance_mpc",
    "Cluster ID": "cluster_id",
}


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


@st.cache_data
def paper_overview(_config: CatalogueConfig, version: tuple[str, float]) -> LibraryOverview:
    return with_paper_library(_config, lambda library: library.overview(), shared_embedder(_config))


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
    return with_paper_library(
        _config,
        lambda library: library.search(query, mode=mode, filters=filters, top_k=SEARCH_RESULTS),
        shared_embedder(_config),
    )


@st.cache_data(show_spinner="Growing the discovery graph...")
def related_papers(
    _config: CatalogueConfig,
    version: tuple[str, float],
    record_id: str,
    categories: tuple[str, ...],
    years: tuple[int, int] | None,
) -> DiscoveryGraph:
    filters = paper_filters(categories, years)
    return with_paper_library(
        _config,
        lambda library: library.related_papers(record_id, filters),
        shared_embedder(_config),
    )


def current_catalogue(config: CatalogueConfig) -> pd.DataFrame:
    path = config.paths.sorted_catalogue
    if not path.is_file():
        return pd.DataFrame()
    return load_catalogue(str(path), path.stat().st_mtime)


def refresh_catalogue(config: CatalogueConfig) -> None:
    with st.spinner("Processing data..."):
        try:
            log = configure_logging(LOGGER_NAME, config.paths.log_file)
            rebuilt = build_sorted_catalogue(config, log.info)
        except Exception as error:
            st.sidebar.error(f"Error updating data: {error}")
            return
    if rebuilt is None:
        st.sidebar.error("Raw catalogue not found. Run the pipeline first.")
        return
    st.cache_data.clear()
    st.rerun()


def sidebar_filters(catalogue: pd.DataFrame) -> tuple[str, str | int, float, str]:
    constellations = [ALL, *sorted(catalogue["constellation"].dropna().unique().tolist())]
    clusters = [ALL, *sorted(catalogue["cluster_id"].dropna().astype(int).unique().tolist())]
    constellation = st.sidebar.selectbox("Constellation", constellations)
    cluster = st.sidebar.selectbox("Cluster ID", clusters)
    min_completeness = st.sidebar.slider("Minimum Completeness (%)", 0.0, 100.0, 0.0, 10.0)
    flag = ALL
    if "quality_flag" in catalogue.columns:
        flags = [ALL, *sorted(catalogue["quality_flag"].dropna().unique().tolist())]
        flag = st.sidebar.selectbox("Quality Flag", flags)
    return constellation, cluster, min_completeness, flag


def render_map(filtered: pd.DataFrame) -> None:
    with st.expander("3D Galaxy Distribution (Click to expand/collapse)", expanded=True):
        color_label = st.selectbox("Select color mapping parameter:", list(COLOR_OPTIONS))
        map_frame = prepare_map_frame(filtered)
        if map_frame.empty:
            st.info("No spatial data available for 3D mapping.")
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
        figure = build_3d_figure(
            map_frame,
            color_column=color_column,
            color_label=color_label,
            color_range=color_range,
            title=f"3D Map (Color: {color_label})",
        )
        st.plotly_chart(figure, width="stretch")


def render_table(filtered: pd.DataFrame) -> None:
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
        st.markdown(
            "<div style='text-align: center; margin-top: 32px;'>"
            f"Page <b>{st.session_state.current_page}</b> of <b>{total_pages}</b></div>",
            unsafe_allow_html=True,
        )
    with previous_column:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        st.button(
            "◀ Prev",
            on_click=previous_page,
            disabled=st.session_state.current_page == 1,
            width="stretch",
        )
    with next_column:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        st.button(
            "Next ▶",
            on_click=next_page,
            disabled=st.session_state.current_page == total_pages,
            width="stretch",
        )
    start = (st.session_state.current_page - 1) * page_size
    st.dataframe(filtered.iloc[start : start + page_size], width="stretch", hide_index=True)


def render_figure(figure, empty_message: str) -> None:
    if figure is None:
        st.info(empty_message)
    else:
        st.pyplot(figure)


def render_analytics(filtered: pd.DataFrame) -> None:
    st.subheader("Statistical Analytics")
    mass_column, radius_column = st.columns(2)
    with mass_column:
        render_figure(stellar_mass_histogram(filtered), "Not enough data to plot Stellar Mass.")
    with radius_column:
        render_figure(effective_radius_histogram(filtered), "Not enough data to plot Effective Radius.")
    render_figure(mass_radius_scatter(filtered), "Not enough data to build Mass vs Radius scatter plot.")


def paper_search_filters(overview: LibraryOverview) -> tuple[tuple[str, ...], tuple[int, int] | None]:
    counts = dict(overview.categories)
    categories = st.multiselect(
        "arXiv categories",
        options=list(counts),
        format_func=lambda category: f"{category} ({counts[category]})",
    )
    years = None
    if len(overview.years) > 1:
        first, last = overview.years[0], overview.years[-1]
        chosen = st.slider("Publication year", first, last, (first, last))
        if tuple(chosen) != (first, last):
            years = (int(chosen[0]), int(chosen[1]))
    return tuple(sorted(categories)), years


def select_seed(record_id: str) -> None:
    st.session_state[SEED_KEY] = record_id


def render_hits(result: DiscoveryResult, mode: str) -> None:
    matched = "" if mode == "semantic" else f" · {result.total_matched} papers contain every keyword"
    st.caption(f"{describe_query(result.chips)}{matched} · {result.elapsed_ms:.0f} ms")
    if "semantic" in result.degraded:
        st.warning("Meaning-based search failed, so only keyword matches are shown.")
    if "semantic" in result.skipped:
        st.caption("Meaning-based search was skipped: the query has no whole word to embed.")
    if not result.hits:
        st.info("No papers match this search.")
    for position, hit in enumerate(result.hits, start=1):
        with st.container(border=True):
            st.markdown(
                f"**{position}. [{escape_markdown(hit.title.strip() or hit.record_id)}]({paper_url(hit.record_id)})**  \n"
                f"{escape_markdown(hit.record_id)} · {publication_year(hit.metadata)} · {match_label(hit)}"
            )
            for snippet in hit.snippets:
                st.markdown(f"*{snippet.field}:* {highlight_markdown(snippet)}")
            st.button("Related papers", key=f"related-{hit.record_id}", on_click=select_seed, args=(hit.record_id,))


def render_graph(graph: DiscoveryGraph) -> None:
    st.subheader("Related Papers")
    st.caption(
        f"{len(graph.nodes)} papers and {len(graph.edges)} links around {graph.seed_record_id}. "
        "Colors mark communities, and the outlined node is the paper you chose."
    )
    if not graph.communities_converged:
        st.caption("The communities are approximate: grouping stopped at its pass limit.")
    st.plotly_chart(build_graph_figure(graph), width="stretch")
    st.dataframe(
        pd.DataFrame(graph_table(graph)),
        width="stretch",
        hide_index=True,
        column_config={"arxiv": st.column_config.LinkColumn("arXiv", display_text="open")},
    )


def render_papers(config: CatalogueConfig, galaxies: pd.DataFrame) -> None:
    st.subheader("Paper Search")
    version = index_version(config)
    if version is None:
        st.info("The paper index is empty. Run `python main.py --index-papers` to index the papers screened so far.")
        return
    if embedding_key_missing(config):
        st.error(f"Set {EMBEDDING_API_KEY_ENV_VAR} to search papers with the openai embeddings provider.")
        return
    overview = paper_overview(config, version)
    st.caption(f"{overview.papers} papers indexed")
    names = sorted(galaxies[KEY_COLUMN].dropna().astype(str).unique().tolist())
    galaxy = st.selectbox("Papers mentioning a galaxy", ["", *names])
    query = st.text_input(
        "Search papers",
        value=galaxy_query(galaxy) if galaxy else "",
        key=f"query-{galaxy}",
        help=QUERY_HELP,
    )
    modes = SEARCH_MODES if config.embeddings.enabled else {"Keyword": "lexical"}
    mode = modes[st.radio("Match by", list(modes), horizontal=True)]
    categories, years = paper_search_filters(overview)
    if query.strip():
        try:
            result = search_papers(config, version, query, mode, categories, years)
        except SearchQueryError as error:
            st.error(f"{error} (column {error.position})")
            return
        render_hits(result, mode)
    seed = st.session_state.get(SEED_KEY)
    if seed:
        render_graph(related_papers(config, version, seed, categories, years))


def main() -> None:
    st.set_page_config(page_title="UDG Research Dashboard", layout="wide")
    config = load_catalogue_config(Path(os.environ.get(CONFIG_ENV_VAR, DEFAULT_CONFIG_PATH)))
    catalogue = current_catalogue(config)

    st.title("Ultra-Diffuse Galaxies (UDG) Research Dashboard")
    st.markdown("Interactive dashboard for analyzing ultra-diffuse galaxies.")
    if catalogue.empty:
        st.warning("Database is empty or file not found. Run the pipeline.")
        return

    st.sidebar.header("Navigation & Filters")
    if st.sidebar.button("Refresh Data", width="stretch"):
        refresh_catalogue(config)
    st.sidebar.divider()
    view_mode = st.sidebar.radio(
        "Display Mode:",
        options=[TABLE_VIEW, ANALYTICS_VIEW, PAPERS_VIEW],
        index=0,
        help="Switch between the galaxy table, statistical plots and a search over the screened papers",
    )
    st.sidebar.divider()

    filtered = filter_catalogue(catalogue, *sidebar_filters(catalogue))
    st.sidebar.markdown(f"**Objects found:** {len(filtered)} out of {len(catalogue)}")
    st.sidebar.download_button(
        label="Download Filtered CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="filtered_udg_database.csv",
        mime="text/csv",
        width="stretch",
    )

    if view_mode == PAPERS_VIEW:
        render_papers(config, filtered)
        return
    render_map(filtered)
    st.divider()
    if filtered.empty:
        st.warning("No data matches the selected filters. Please adjust the parameters in the sidebar.")
    elif view_mode == TABLE_VIEW:
        render_table(filtered)
    else:
        render_analytics(filtered)


main()
