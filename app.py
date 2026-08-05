import streamlit as st
import pandas as pd
import plotly.express as px
import matplotlib.pyplot as plt
import seaborn as sns
import os
import numpy as np

from main import process_database 

st.set_page_config(page_title="UDG Research Dashboard", layout="wide")

CSV_SORTED = "udg_database_sorted.csv"

@st.cache_data
def load_data() -> pd.DataFrame:
    if os.path.exists(CSV_SORTED):
        return pd.read_csv(CSV_SORTED)
    return pd.DataFrame()

@st.cache_data
def filter_dataframe(df: pd.DataFrame, constellation: str, cluster: str, min_comp: float, flag: str) -> pd.DataFrame:
    filtered = df.copy()
    if constellation != "All":
        filtered = filtered[filtered["constellation"] == constellation]
    if cluster != "All":
        filtered = filtered[filtered["cluster_id"] == cluster]
    filtered = filtered[filtered["completeness_pct"] >= min_comp]
    if flag != "All":
        filtered = filtered[filtered["quality_flag"] == flag]
    return filtered

@st.cache_data
def prepare_map_data(filtered_df: pd.DataFrame) -> pd.DataFrame:
    map_df = filtered_df.dropna(subset=["ra", "dec", "distance_mpc"]).copy()
    if map_df.empty:
        return map_df

    if "dark_matter_fraction" in map_df.columns:
        map_df["dark_matter_fraction"] = map_df["dark_matter_fraction"].clip(0.0, 1.0)

    ra_rad = np.deg2rad(map_df["ra"])
    dec_rad = np.deg2rad(map_df["dec"])
    r_visual = np.sqrt(map_df["distance_mpc"])

    map_df["x"] = r_visual * np.cos(dec_rad) * np.cos(ra_rad)
    map_df["y"] = r_visual * np.cos(dec_rad) * np.sin(ra_rad)
    map_df["z"] = r_visual * np.sin(dec_rad)
    map_df["size_visual"] = np.sqrt(map_df.get("effective_radius_kpc", 1).fillna(1)) * 5

    map_df["hover_constellation"] = map_df.get("constellation", pd.Series(["Unknown"]*len(map_df))).fillna("Unknown")
    map_df["hover_cluster"] = map_df.get("cluster_id", pd.Series([-1]*len(map_df))).apply(lambda x: "Single" if pd.isna(x) or x == -1 else f"Cluster #{int(x)}")
    map_df["hover_completeness"] = map_df.get("completeness_pct", pd.Series([0]*len(map_df))).apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
    map_df["hover_ra"] = map_df["ra"].apply(lambda x: f"{x:.4f}°" if pd.notna(x) else "N/A")
    map_df["hover_dec"] = map_df["dec"].apply(lambda x: f"{x:.4f}°" if pd.notna(x) else "N/A")
    map_df["hover_dist"] = map_df["distance_mpc"].apply(lambda x: f"{x:.2f} Mpc" if pd.notna(x) else "N/A")
    map_df["hover_reff"] = map_df.get("effective_radius_kpc", pd.Series([np.nan]*len(map_df))).apply(lambda x: f"{x:.2f} kpc" if pd.notna(x) else "N/A")
    map_df["hover_mass"] = map_df.get("stellar_mass_solar", pd.Series([np.nan]*len(map_df))).apply(lambda x: f"{x:.2e} M☉" if pd.notna(x) and not pd.isna(x) else "N/A")
    map_df["hover_dm"] = map_df.get("dark_matter_fraction", pd.Series([np.nan]*len(map_df))).apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "N/A")

    return map_df

@st.cache_resource
def create_plotly_fig(map_df, plot_color_col, selected_color_label, range_col):
    custom_data_cols = [
        "hover_constellation", "hover_cluster", "hover_completeness", 
        "hover_ra", "hover_dec", "hover_dist", "hover_reff", "hover_mass", "hover_dm"
    ]
    
    fig = px.scatter_3d(
        map_df, x="x", y="y", z="z",
        color=plot_color_col,
        size="size_visual",
        hover_name="galaxy_name",
        custom_data=custom_data_cols,
        color_continuous_scale="Viridis",
        range_color=range_col,
        title=f"3D Map (Color: {selected_color_label})",
        labels={
            "x": "X Axis [Mpc]",
            "y": "Y Axis [Mpc]",
            "z": "Z Axis [Mpc]",
            plot_color_col: selected_color_label
        }
    )
    
    fig.update_traces(
        hovertemplate=(
            "<b>%{hovertext}</b><br><br>"
            "<b>Constellation:</b> %{customdata[0]}<br>"
            "<b>Cluster Status:</b> %{customdata[1]}<br>"
            "<b>Completeness:</b> %{customdata[2]}<br>"
            "--------------------------------<br>"
            "<b>Coordinates:</b> RA %{customdata[3]} | Dec %{customdata[4]}<br>"
            "<b>Distance:</b> %{customdata[5]}<br>"
            "<b>Effective Radius:</b> %{customdata[6]}<br>"
            "<b>Stellar Mass:</b> %{customdata[7]}<br>"
            "<b>Dark Matter:</b> %{customdata[8]}<extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark", 
        margin=dict(l=0, r=0, b=0, t=40),
        scene=dict(
            xaxis_title="X Position [Mpc]",
            yaxis_title="Y Position [Mpc]",
            zaxis_title="Z Position [Mpc]"
        )
    )
    return fig

df = load_data()

st.title("Ultra-Diffuse Galaxies (UDG) Research Dashboard")
st.markdown("Interactive dashboard for analyzing ultra-diffuse galaxies.")

if df.empty:
    st.warning("Database is empty or file not found. Run the pipeline.")
else:
    st.sidebar.header("Navigation & Filters")
    
    if st.sidebar.button("Refresh Data", use_container_width=True):
        with st.spinner("Processing data..."):
            try:
                process_database()
                st.cache_data.clear()
                st.cache_resource.clear()
                st.success("Data updated successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Error updating data: {e}")
                
    st.sidebar.divider()
    
    view_mode = st.sidebar.radio(
        "Display Mode:",
        options=["Data Table", "Analytics"],
        index=0,
        help="Switch between tabular view and statistical plots"
    )
    
    st.sidebar.divider()
    
    constellations = ["All"] + sorted(df["constellation"].dropna().unique().tolist())
    selected_constellation = st.sidebar.selectbox("Constellation", constellations)
    
    clusters = ["All"] + sorted(df["cluster_id"].dropna().unique().astype(int).tolist())
    selected_cluster = st.sidebar.selectbox("Cluster ID", clusters)
    
    min_completeness = st.sidebar.slider("Minimum Completeness (%)", 0.0, 100.0, 0.0, 10.0)
    
    if "quality_flag" in df.columns:
        flags = ["All"] + sorted(df["quality_flag"].dropna().unique().tolist())
        selected_flag = st.sidebar.selectbox("Quality Flag", flags)
    else:
        selected_flag = "All"

    filtered_df = filter_dataframe(df, selected_constellation, selected_cluster, min_completeness, selected_flag)

    st.sidebar.markdown(f"**Objects found:** {len(filtered_df)} out of {len(df)}")

    csv_data = filtered_df.to_csv(index=False).encode("utf-8")
    st.sidebar.download_button(
        label="Download Filtered CSV",
        data=csv_data,
        file_name="filtered_udg_database.csv",
        mime="text/csv",
        use_container_width=True
    )

    with st.expander("3D Galaxy Distribution (Click to expand/collapse)", expanded=True):
        color_options = {
            "Dark Matter Fraction": "dark_matter_fraction",
            "Completeness (%)": "completeness_pct",
            "Distance (Mpc)": "distance_mpc",
            "Cluster ID": "cluster_id"
        }
        selected_color_label = st.selectbox("Select color mapping parameter:", list(color_options.keys()))
        color_column = color_options[selected_color_label]

        map_df = prepare_map_data(filtered_df)
        
        if not map_df.empty:
            if color_column == "cluster_id":
                map_df["cluster_id_str"] = map_df["cluster_id"].apply(
                    lambda x: f"Cluster {int(x)}" if x != -1 else "Unclustered"
                )
                plot_color_col = "cluster_id_str"
                range_col = None 
            else:
                plot_color_col = color_column
                if color_column == "dark_matter_fraction":
                    range_col = [0.0, 1.0]
                elif color_column == "distance_mpc":
                    max_dist = map_df["distance_mpc"].quantile(0.99)
                    min_dist = map_df["distance_mpc"].min()
                    range_col = [min_dist, max_dist]
                else:
                    range_col = None

            fig = create_plotly_fig(map_df, plot_color_col, selected_color_label, range_col)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No spatial data available for 3D mapping.")

    st.divider()

    if filtered_df.empty:
        st.warning("No data matches the selected filters. Please adjust the parameters in the sidebar.")
    else:
        if view_mode == "Data Table":
            st.subheader("Data Table")
            
            if "current_page" not in st.session_state:
                st.session_state.current_page = 1

            def reset_page():
                st.session_state.current_page = 1

            def prev_page():
                st.session_state.current_page -= 1

            def next_page():
                st.session_state.current_page += 1

            col_size, col_info, col_prev, col_next = st.columns([1, 2, 1, 1])

            with col_size:
                page_size = st.selectbox("Objects per page:", options=[10, 50, 100], index=0, on_change=reset_page)

            total_pages = max(1, (len(filtered_df) - 1) // page_size + 1)

            if st.session_state.current_page > total_pages:
                st.session_state.current_page = total_pages

            with col_info:
                st.markdown(f"<div style='text-align: center; margin-top: 32px;'>Page <b>{st.session_state.current_page}</b> of <b>{total_pages}</b></div>", unsafe_allow_html=True)

            with col_prev:
                st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                st.button("◀ Prev", on_click=prev_page, disabled=(st.session_state.current_page == 1), use_container_width=True)

            with col_next:
                st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                st.button("Next ▶", on_click=next_page, disabled=(st.session_state.current_page == total_pages), use_container_width=True)

            start_idx = (st.session_state.current_page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_df = filtered_df.iloc[start_idx:end_idx]

            st.dataframe(paginated_df, use_container_width=True, hide_index=True)

        elif view_mode == "Analytics":
            st.subheader("Statistical Analytics")
            
            sns.set_theme(style="darkgrid")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Stellar Mass Distribution")
                if "stellar_mass_solar" in filtered_df.columns and filtered_df["stellar_mass_solar"].notna().sum() > 0:
                    fig1, ax1 = plt.subplots(figsize=(6, 4))
                    sns.histplot(filtered_df["stellar_mass_solar"].dropna(), log_scale=True, kde=False, color="purple", ax=ax1)
                    ax1.set_xlabel(r"Stellar Mass ($M_\odot$)")
                    ax1.set_ylabel("Count")
                    st.pyplot(fig1)
                else:
                    st.info("Not enough data to plot Stellar Mass.")
                    
            with col2:
                st.markdown("#### Effective Radius Distribution")
                if "effective_radius_kpc" in filtered_df.columns and filtered_df["effective_radius_kpc"].notna().sum() > 0:
                    fig2, ax2 = plt.subplots(figsize=(6, 4))
                    sns.histplot(filtered_df["effective_radius_kpc"].dropna(), log_scale=True, kde=False, color="teal", ax=ax2)
                    ax2.set_xlabel(r"$R_{eff}$ [kpc]")
                    ax2.set_ylabel("Count")
                    st.pyplot(fig2)
                else:
                    st.info("Not enough data to plot Effective Radius.")
            
            st.markdown("#### Stellar Mass vs Effective Radius")
            valid_scatter_data = filtered_df.dropna(subset=["stellar_mass_solar", "effective_radius_kpc"])
            
            if {"stellar_mass_solar", "effective_radius_kpc", "completeness_pct"}.issubset(filtered_df.columns) and not valid_scatter_data.empty:
                fig3, ax3 = plt.subplots(figsize=(10, 5))
                sns.scatterplot(
                    data=filtered_df,
                    x="effective_radius_kpc",
                    y="stellar_mass_solar",
                    hue="completeness_pct",
                    palette="viridis",
                    alpha=0.7,
                    ax=ax3
                )
                ax3.set_xscale("log")
                ax3.set_yscale("log")
                ax3.set_xlabel(r"$R_{eff}$ [kpc]")
                ax3.set_ylabel(r"Stellar Mass ($M_\odot$)")
                ax3.legend(title="Completeness %", loc="upper left", bbox_to_anchor=(1, 1))
                
                plt.tight_layout()
                st.pyplot(fig3)
            else:
                st.info("Not enough data to build Mass vs Radius scatter plot.")