from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
from sci_etl_core import configure_logging

from udg_catalogue.analytics import effective_radius_histogram, mass_radius_scatter, stellar_mass_histogram
from udg_catalogue.config import CatalogueConfig, load_catalogue_config
from udg_catalogue.maps import build_3d_figure, cluster_label, prepare_map_frame
from udg_catalogue.postprocess import build_sorted_catalogue, read_catalogue

ALL = "All"
LOGGER_NAME = "UDGPipeline"
TABLE_VIEW = "Data Table"
ANALYTICS_VIEW = "Analytics"
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


def main() -> None:
    st.set_page_config(page_title="UDG Research Dashboard", layout="wide")
    config = load_catalogue_config()
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
        options=[TABLE_VIEW, ANALYTICS_VIEW],
        index=0,
        help="Switch between tabular view and statistical plots",
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

    render_map(filtered)
    st.divider()
    if filtered.empty:
        st.warning("No data matches the selected filters. Please adjust the parameters in the sidebar.")
    elif view_mode == TABLE_VIEW:
        render_table(filtered)
    else:
        render_analytics(filtered)


main()
