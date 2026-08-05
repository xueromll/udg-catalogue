import os
import shutil
import re
import pandas as pd
import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from sklearn.cluster import DBSCAN

from config import CSV_FILE, SORTED_CSV_FILE, PROCESSED_FILE, KEY_FIELDS, MAX_DIST_MPC, MIN_SAMPLES
from logger import logger

FORBIDDEN_KEYWORDS = [
    "sim", "simulation", "mock", "synthetic", "toy", "model", "tng", 
    "illustris", "fire", "eagle", "romulus", "nihao", "gadget", "gizmo", 
    "subhalo", "test", "example", "idealized", "artific"
]
FORBIDDEN_PATTERN = re.compile(
    r"\b(" + "|".join(FORBIDDEN_KEYWORDS) + r")\b|^(" + "|".join(FORBIDDEN_KEYWORDS) + r")[-_0-9]",
    re.IGNORECASE
)

def universal_normalize_name(name: str) -> str:
    if not name or pd.isna(name):
        return ""
    s = str(name).strip().lower()
    s = re.sub(r"\bdf\s*(?=\d)", "dragonfly", s)
    s = re.sub(r"^df(?=\d)", "dragonfly", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    s = re.sub(r"(?<=[a-z])0+(?=\d)", "", s)
    return s

def load_processed_ids() -> set[str]:
    if not os.path.isfile(PROCESSED_FILE):
        return set()
    try:
        processed = set()
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                clean_id = line.split("/abs/")[-1] if "/abs/" in line else (line.split("/pdf/")[-1].replace(".pdf", "") if "/pdf/" in line else line)
                processed.add(clean_id)
        return processed
    except Exception as e:
        logger.error(f"Error reading processed_ids: {e}")
        return set()

def save_processed_id(arxiv_id: str) -> None:
    if arxiv_id:
        with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
            f.write(arxiv_id + "\n")

def is_valid_galaxy(galaxy: dict) -> bool:
    if not galaxy or not isinstance(galaxy, dict):
        return False
    name = str(galaxy.get("galaxy_name", "")).strip()
    if not name or name.lower() in ["null", "none", "unknown", "n/a", "nan"]:
        return False

    if FORBIDDEN_PATTERN.search(name):
        logger.info(f"Object '{name}' filtered out as simulation/model.")
        return False

    ra, dec = galaxy.get("ra"), galaxy.get("dec")
    if ra is not None:
        try:
            if not (0.0 <= float(ra) <= 360.0): 
                return False
        except (ValueError, TypeError): 
            return False

    if dec is not None:
        try:
            if not (-90.0 <= float(dec) <= 90.0): 
                return False
        except (ValueError, TypeError): 
            return False

    return any(galaxy.get(f) is not None for f in KEY_FIELDS)

def clean_duplicates(csv_file: str = CSV_FILE, max_sep_arcsec: float = 3.0) -> None:
    try:
        if not os.path.isfile(csv_file):
            return

        shutil.copyfile(csv_file, csv_file + ".bak")
        logger.info(f"Database backup created: {csv_file}.bak")

        df = pd.read_csv(csv_file)
        if df.empty:
            return

        initial_count = len(df)
        columns_to_merge = [c for c in df.columns if c != "galaxy_name"]
        df["_norm_name"] = df["galaxy_name"].apply(universal_normalize_name)

        df_stage1 = df.groupby("_norm_name", as_index=False).first()
        for col in columns_to_merge:
            if col in df.columns:
                agg_vals = df.groupby("_norm_name")[col].first()
                df_stage1[col] = df_stage1["_norm_name"].map(agg_vals)

        valid_coords = df_stage1["ra"].notna() & df_stage1["dec"].notna()
        if valid_coords.sum() > 1:
            coords = SkyCoord(
                ra=df_stage1.loc[valid_coords, "ra"].values * u.deg,
                dec=df_stage1.loc[valid_coords, "dec"].values * u.deg
            )
            idx, d2d, _ = coords.match_to_catalog_sky(coords, nthneighbor=2)
            sep_arcsec = d2d.to(u.arcsec).value
            
            valid_indices = df_stage1.index[valid_coords].to_numpy()
            drop_indices = set()
            
            for local_i, neighbor_local_j in enumerate(idx):
                if sep_arcsec[local_i] <= max_sep_arcsec:
                    orig_i = valid_indices[local_i]
                    orig_j = valid_indices[neighbor_local_j]
                    if orig_i < orig_j and orig_j not in drop_indices:
                        for col in columns_to_merge:
                            if pd.isna(df_stage1.at[orig_i, col]) and pd.notna(df_stage1.at[orig_j, col]):
                                df_stage1.at[orig_i, col] = df_stage1.at[orig_j, col]
                        drop_indices.add(orig_j)
            
            df_stage1 = df_stage1.drop(index=list(drop_indices))

        df_final = df_stage1.drop(columns=["_norm_name"])
        df_final.to_csv(csv_file, index=False, encoding="utf-8")
        logger.info(f"Cleanup completed. Duplicates removed: {initial_count - len(df_final)} | Database total: {len(df_final)}")
    except Exception as e:
        logger.error(f"Error during auto-cleanup: {e}")

def upsert_to_csv(records: list[dict]) -> None:
    if not records: 
        return
    fieldnames = ["galaxy_name"] + KEY_FIELDS
    df = pd.read_csv(CSV_FILE) if os.path.isfile(CSV_FILE) and os.path.getsize(CSV_FILE) > 0 else pd.DataFrame(columns=fieldnames)
    
    for col in fieldnames:
        if col not in df.columns: 
            df[col] = None

    df["_norm_name"] = df["galaxy_name"].apply(universal_normalize_name)
    new_rows, updated_count, added_count = [], 0, 0

    for rec in records:
        if not is_valid_galaxy(rec): 
            continue
        raw_name = rec.get("galaxy_name")
        norm_name = universal_normalize_name(raw_name)
        if not norm_name: 
            continue

        match_mask = df["_norm_name"] == norm_name
        if match_mask.any():
            idx = df[match_mask].index[0]
            was_updated = False
            for col in KEY_FIELDS:
                new_val = rec.get(col)
                if new_val is not None:
                    try:
                        if pd.isna(df.at[idx, col]):
                            val_float = float(new_val)
                            if col == "dark_matter_fraction":
                                val_float = min(max(val_float, 0.0), 1.0)
                            df.at[idx, col] = val_float
                            was_updated = True
                    except (ValueError, TypeError): 
                        continue
            if was_updated: 
                updated_count += 1
        else:
            new_row = {"galaxy_name": raw_name, "_norm_name": norm_name}
            for col in KEY_FIELDS:
                val = rec.get(col)
                try: 
                    if val is not None:
                        val_float = float(val)
                        if col == "dark_matter_fraction":
                            val_float = min(max(val_float, 0.0), 1.0)
                        new_row[col] = val_float
                    else:
                        new_row[col] = None
                except (ValueError, TypeError): 
                    new_row[col] = None
            new_rows.append(new_row)
            added_count += 1

    if new_rows: 
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
    df.drop(columns=["_norm_name"]).to_csv(CSV_FILE, index=False, encoding="utf-8")
    if added_count > 0 or updated_count > 0:
        logger.info(f"CSV UPDATE -> Added new: {added_count} | Filled missing values: {updated_count}")

def calculate_completeness(df: pd.DataFrame) -> pd.DataFrame:
    existing_fields = [c for c in KEY_FIELDS if c in df.columns]
    if not existing_fields:
        df["completeness_pct"] = 0
        return df
    filled_count = df[existing_fields].notna().sum(axis=1)
    df["filled_fields"] = filled_count
    df["completeness_pct"] = (filled_count / len(existing_fields) * 100).round(1)
    return df

def assign_constellations(df: pd.DataFrame) -> pd.DataFrame:
    df["constellation"] = "Unknown"
    valid_coords = df["ra"].notna() & df["dec"].notna()
    if not valid_coords.any(): 
        return df

    try:
        coords = SkyCoord(
            ra=df.loc[valid_coords, "ra"].values * u.deg,
            dec=df.loc[valid_coords, "dec"].values * u.deg,
            frame="icrs"
        )
        df.loc[valid_coords, "constellation"] = coords.get_constellation(short_name=False)
    except Exception as e:
        logger.warning(f"Astropy constellation mapping failed: {e}. Trying Skyfield fallback...")
        try:
            from skyfield.api import Loader
            load = Loader('skyfield_data')
            ts = load.timescale()
            constellations_list = ["Unknown" for _ in range(valid_coords.sum())]
            df.loc[valid_coords, "constellation"] = constellations_list
        except Exception as ex:
            logger.error(f"Skyfield fallback also failed: {ex}")
    return df

def assign_3d_clusters(df: pd.DataFrame, max_dist_mpc: float = MAX_DIST_MPC, min_samples: int = MIN_SAMPLES) -> pd.DataFrame:
    df["cluster_id"] = -1
    valid_3d = df["ra"].notna() & df["dec"].notna() & df["distance_mpc"].notna()
    if valid_3d.sum() < min_samples: 
        return df

    ra_rad = np.deg2rad(df.loc[valid_3d, "ra"])
    dec_rad = np.deg2rad(df.loc[valid_3d, "dec"])
    dist = df.loc[valid_3d, "distance_mpc"]

    x = dist * np.cos(dec_rad) * np.cos(ra_rad)
    y = dist * np.cos(dec_rad) * np.sin(ra_rad)
    z = dist * np.sin(dec_rad)

    db = DBSCAN(eps=max_dist_mpc, min_samples=min_samples).fit(np.column_stack((x, y, z)))
    df.loc[valid_3d, "cluster_id"] = db.labels_
    return df

def assign_quality_flag(df: pd.DataFrame) -> pd.DataFrame:
    def get_flag(pct: float) -> str:
        if pd.isna(pct):
            return "Low Confidence"
        if pct == 100.0:
            return "Confirmed"
        elif pct >= 50.0:
            return "Needs Review"
        else:
            return "Low Confidence"
    df["quality_flag"] = df["completeness_pct"].apply(get_flag)
    return df

def process_database() -> None:
    if not os.path.isfile(CSV_FILE):
        logger.error(f"File {CSV_FILE} not found!")
        return

    df = pd.read_csv(CSV_FILE)
    if df.empty:
        logger.warning("Database is empty.")
        return

    logger.info("=== PROCESSING AND SORTING DATABASE ===")
    logger.info(f"Loaded objects: {len(df)}")

    if "dark_matter_fraction" in df.columns:
        df["dark_matter_fraction"] = df["dark_matter_fraction"].clip(0.0, 1.0)

    df = calculate_completeness(df)
    df = assign_constellations(df)
    df = assign_3d_clusters(df)
    df = assign_quality_flag(df)

    df_sorted = df.sort_values(
        by=["completeness_pct", "constellation", "cluster_id", "galaxy_name"],
        ascending=[False, True, True, True]
    )

    first_cols = ["galaxy_name", "completeness_pct", "quality_flag", "constellation", "cluster_id"]
    df_sorted = df_sorted[first_cols + [c for c in df_sorted.columns if c not in first_cols]]
    df_sorted.to_csv(SORTED_CSV_FILE, index=False, encoding="utf-8")

    logger.info(f"Total objects in database: {len(df_sorted)}")
    logger.info(f"Objects with 100% completeness: {(df_sorted['completeness_pct'] == 100).sum()}")
    logger.info(f"Constellations found: {df_sorted[df_sorted['constellation'] != 'Unknown']['constellation'].nunique()}")
    logger.info(f"3D clusters formed: {df_sorted[df_sorted['cluster_id'] != -1]['cluster_id'].nunique()}")
    logger.info(f"Sorted database saved -> {SORTED_CSV_FILE}")