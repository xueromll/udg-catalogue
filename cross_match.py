import pandas as pd
import astropy.units as u
from astropy.coordinates import SkyCoord
from logger import logger

def cross_match_catalogs(our_csv: str, ref_csv: str, max_sep_arcsec: float = 3.0) -> pd.DataFrame:
    try:
        df_our = pd.read_csv(our_csv).dropna(subset=["ra", "dec"])
        df_ref = pd.read_csv(ref_csv).dropna(subset=["ra", "dec"])
        
        if df_our.empty or df_ref.empty:
            logger.warning("One of the catalogs is empty for cross-matching.")
            return pd.DataFrame()

        coord_our = SkyCoord(ra=df_our["ra"].values * u.deg, dec=df_our["dec"].values * u.deg)
        coord_ref = SkyCoord(ra=df_ref["ra"].values * u.deg, dec=df_ref["dec"].values * u.deg)
        
        idx, d2d, _ = coord_our.match_to_catalog_sky(coord_ref)
        sep_arcsec = d2d.to(u.arcsec).value
        
        matched_mask = sep_arcsec <= max_sep_arcsec
        
        df_our["matched_with_ref"] = matched_mask
        df_our["separation_arcsec"] = sep_arcsec
        
        matched_df = df_our[matched_mask].copy()
        logger.info(f"Cross-matching completed. Matched objects: {len(matched_df)} out of {len(df_our)}")
        return matched_df
    except Exception as e:
        logger.error(f"Error during catalog cross-matching: {e}")
        return pd.DataFrame()