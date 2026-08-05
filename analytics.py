import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from logger import logger

def generate_analytics_report(csv_file: str, output_dir: str = "analysis") -> None:
    os.makedirs(output_dir, exist_ok=True)
    if not os.path.exists(csv_file):
        logger.warning(f"File {csv_file} not found for analytics.")
        return

    df = pd.read_csv(csv_file)
    df.columns = df.columns.str.strip()
    sns.set_theme(style="darkgrid")

    if "stellar_mass_solar" in df.columns and df["stellar_mass_solar"].notna().sum() > 0:
        plt.figure(figsize=(8, 5))
        sns.histplot(df["stellar_mass_solar"].dropna(), log_scale=True, kde=False, color="purple")
        plt.title("Stellar Mass Distribution (Solar Masses)")
        plt.xlabel(r"Stellar Mass ($M_\odot$)")
        plt.savefig(os.path.join(output_dir, "stellar_mass_dist.png"), dpi=300)
        plt.close()

    if "effective_radius_kpc" in df.columns and df["effective_radius_kpc"].notna().sum() > 0:
        plt.figure(figsize=(8, 5))
        sns.histplot(df["effective_radius_kpc"].dropna(), log_scale=True, kde=False, color="teal")
        plt.title("Effective Radius Distribution")
        plt.xlabel(r"$R_{eff}$ [kpc]")
        plt.savefig(os.path.join(output_dir, "radius_dist.png"), dpi=300)
        plt.close()

    if {"stellar_mass_solar", "effective_radius_kpc"}.issubset(df.columns):
        plt.figure(figsize=(8, 5))

        sns.scatterplot(
            data=df,
            x="effective_radius_kpc",
            y="stellar_mass_solar",
            hue="completeness_pct",
            palette="viridis",
            alpha=0.7
        )
        plt.xscale("log")
        plt.yscale("log")
        plt.title("Stellar Mass vs Effective Radius")
        plt.xlabel(r"$R_{eff}$ [kpc]")
        plt.ylabel(r"Stellar Mass ($M_\odot$)")
        
        plt.legend(title="Completeness %", loc="upper left")
        plt.savefig(os.path.join(output_dir, "mass_vs_radius.png"), dpi=300)
        plt.close()

    logger.info(f"Analytics reports successfully saved to {output_dir}/")