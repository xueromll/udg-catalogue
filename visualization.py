import os
import pandas as pd
import numpy as np
import plotly.express as px

from config import CSV_FILE, SORTED_CSV_FILE, HTML_MAP_FILE
from logger import logger

def visualize_udg_3d(csv_file: str = SORTED_CSV_FILE, html_output_file: str = HTML_MAP_FILE) -> None:
    target_csv = csv_file if os.path.isfile(csv_file) else CSV_FILE
    if not os.path.isfile(target_csv):
        logger.warning("Visualization failed: database is empty/missing.")
        return

    df_full = pd.read_csv(target_csv)
    df = df_full.dropna(subset=["ra", "dec", "distance_mpc"]).copy()
    if df.empty:
        logger.warning("Visualization failed: missing spatial coordinates.")
        return

    df["hover_constellation"] = df.get("constellation", pd.Series(["Unknown"]*len(df))).fillna("Unknown")
    df["hover_cluster"] = df.get("cluster_id", pd.Series([-1]*len(df))).apply(lambda x: "Single / Unclustered" if pd.isna(x) or x == -1 else f"Cluster #{int(x)}")
    df["hover_completeness"] = df.get("completeness_pct", pd.Series([0]*len(df))).apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
    df["hover_ra"] = df["ra"].apply(lambda x: f"{x:.4f}°" if pd.notna(x) else "N/A")
    df["hover_dec"] = df["dec"].apply(lambda x: f"{x:.4f}°" if pd.notna(x) else "N/A")
    df["hover_dist"] = df["distance_mpc"].apply(lambda x: f"{x:.2f} Mpc" if pd.notna(x) else "N/A")
    df["hover_reff"] = df.get("effective_radius_kpc", pd.Series([np.nan]*len(df))).apply(lambda x: f"{x:.2f} kpc" if pd.notna(x) else "N/A")
    df["hover_mass"] = df.get("stellar_mass_solar", pd.Series([np.nan]*len(df))).apply(lambda x: f"{x:.2e} M☉" if pd.notna(x) and not pd.isna(x) else "N/A")
    df["hover_dm"] = df.get("dark_matter_fraction", pd.Series([np.nan]*len(df))).apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "N/A")

    df["size_visual"] = np.sqrt(df["effective_radius_kpc"].fillna(1)) * 5
    df["dm_color"] = df["dark_matter_fraction"].fillna(0).clip(0.0, 1.0)

    ra_rad, dec_rad = np.deg2rad(df["ra"]), np.deg2rad(df["dec"])
    r_visual = np.sqrt(df["distance_mpc"])

    df["x"] = r_visual * np.cos(dec_rad) * np.cos(ra_rad)
    df["y"] = r_visual * np.cos(dec_rad) * np.sin(ra_rad)
    df["z"] = r_visual * np.sin(dec_rad)

    custom_data_cols = ["hover_constellation", "hover_cluster", "hover_completeness", "hover_ra", "hover_dec", "hover_dist", "hover_reff", "hover_mass", "hover_dm"]

    fig = px.scatter_3d(
        df, x="x", y="y", z="z", color="dm_color", size="size_visual",
        hover_name="galaxy_name", custom_data=custom_data_cols,
        title=f"3D Distribution of Ultra-Diffuse Galaxies (N = {len(df)})",
        color_continuous_scale="Viridis", range_color=[0.0, 1.0], labels={"dm_color": "DM Fraction"}
    )

    fig.update_traces(
        marker=dict(sizemode="diameter", sizeref=1, sizemin=3),
        hovertemplate=(
            "<b>%{hovertext}</b><br><br>"
            "<b>Constellation:</b> %{customdata[0]}<br>"
            "<b>Cluster Status:</b> %{customdata[1]}<br>"
            "<b>Data Completeness:</b> %{customdata[2]}<br>"
            "--------------------------------<br>"
            "<b>Coordinates:</b> RA %{customdata[3]} | Dec %{customdata[4]}<br>"
            "<b>Distance:</b> %{customdata[5]}<br>"
            "<b>Effective Radius (R_eff):</b> %{customdata[6]}<br>"
            "<b>Stellar Mass:</b> %{customdata[7]}<br>"
            "<b>Dark Matter Fraction:</b> %{customdata[8]}<extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#0b0f19", plot_bgcolor="#0b0f19",
        scene=dict(
            xaxis=dict(gridcolor="#1e293b", title="X Position [Mpc]"),
            yaxis=dict(gridcolor="#1e293b", title="Y Position [Mpc]"),
            zaxis=dict(gridcolor="#1e293b", title="Z Position [Mpc]"),
            bgcolor="#0a0f1e", aspectmode="cube"
        ),
        margin=dict(l=0, r=0, b=0, t=50)
    )

    fig.write_html(html_output_file)
    logger.info(f"3D map updated -> {html_output_file}")