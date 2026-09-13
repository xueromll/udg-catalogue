from __future__ import annotations

from collections.abc import Sequence

import astropy.units as u
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
from sci_etl_core.processors import FeatureExtractor, NeighborMatcher, Processor

UNKNOWN_CONSTELLATION = "Unknown"


def located_rows(frame: pd.DataFrame, ra_column: str = "ra", dec_column: str = "dec") -> pd.Series:
    if ra_column not in frame.columns or dec_column not in frame.columns:
        return pd.Series(False, index=frame.index)
    ra = pd.to_numeric(frame[ra_column], errors="coerce")
    dec = pd.to_numeric(frame[dec_column], errors="coerce")
    return ra.between(0.0, 360.0) & dec.between(-90.0, 90.0)


def sky_coordinates(frame: pd.DataFrame, ra_column: str = "ra", dec_column: str = "dec") -> SkyCoord:
    return SkyCoord(
        ra=frame[ra_column].to_numpy(dtype=float) * u.deg,
        dec=frame[dec_column].to_numpy(dtype=float) * u.deg,
        frame="icrs",
    )


def cartesian_coordinates(
    ra_degrees: Sequence[float] | pd.Series,
    dec_degrees: Sequence[float] | pd.Series,
    radius: Sequence[float] | pd.Series,
) -> np.ndarray:
    ra = np.deg2rad(np.asarray(ra_degrees, dtype=float))
    dec = np.deg2rad(np.asarray(dec_degrees, dtype=float))
    distance = np.asarray(radius, dtype=float)
    return np.column_stack(
        (
            distance * np.cos(dec) * np.cos(ra),
            distance * np.cos(dec) * np.sin(ra),
            distance * np.sin(dec),
        )
    )


class SkyPositionMatcher(NeighborMatcher):
    def __init__(self, ra_column: str = "ra", dec_column: str = "dec") -> None:
        self._ra_column = ra_column
        self._dec_column = dec_column

    def find_matches(self, frame: pd.DataFrame, threshold: float) -> list[tuple[int, int]]:
        located = frame[located_rows(frame, self._ra_column, self._dec_column)]
        if len(located) < 2:
            return []
        coordinates = sky_coordinates(located, self._ra_column, self._dec_column)
        neighbours, separations, _ = coordinates.match_to_catalog_sky(coordinates, nthneighbor=2)
        separation_arcsec = separations.to_value(u.arcsec)
        labels = located.index.to_numpy()
        return [
            (int(labels[position]), int(labels[neighbour]))
            for position, neighbour in enumerate(neighbours)
            if separation_arcsec[position] <= threshold and labels[position] < labels[neighbour]
        ]


class CartesianDistanceFeatures(FeatureExtractor):
    def __init__(
        self,
        distance_column: str = "distance_mpc",
        ra_column: str = "ra",
        dec_column: str = "dec",
    ) -> None:
        self._distance_column = distance_column
        self._ra_column = ra_column
        self._dec_column = dec_column

    def extract(self, frame: pd.DataFrame) -> tuple[np.ndarray, pd.Index]:
        if self._distance_column not in frame.columns:
            return np.empty((0, 3)), frame.index[:0]
        distance = pd.to_numeric(frame[self._distance_column], errors="coerce")
        usable = located_rows(frame, self._ra_column, self._dec_column) & distance.notna()
        features = cartesian_coordinates(
            frame.loc[usable, self._ra_column],
            frame.loc[usable, self._dec_column],
            distance[usable],
        )
        return features, frame.index[usable.to_numpy()]


class ConstellationStep(Processor):
    def __init__(
        self,
        output_column: str = "constellation",
        ra_column: str = "ra",
        dec_column: str = "dec",
    ) -> None:
        self._output_column = output_column
        self._ra_column = ra_column
        self._dec_column = dec_column

    def process(self, frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        frame[self._output_column] = UNKNOWN_CONSTELLATION
        located = located_rows(frame, self._ra_column, self._dec_column)
        if located.any():
            coordinates = sky_coordinates(frame.loc[located], self._ra_column, self._dec_column)
            frame.loc[located, self._output_column] = coordinates.get_constellation(short_name=False)
        return frame


def cross_match_catalogues(
    catalogue: pd.DataFrame,
    reference: pd.DataFrame,
    max_separation_arcsec: float = 3.0,
) -> pd.DataFrame:
    ours = catalogue[located_rows(catalogue)].copy()
    theirs = reference[located_rows(reference)]
    if ours.empty or theirs.empty:
        return ours.assign(separation_arcsec=np.nan, matched_with_ref=False).iloc[0:0]
    _, separations, _ = sky_coordinates(ours).match_to_catalog_sky(sky_coordinates(theirs))
    ours["separation_arcsec"] = separations.to_value(u.arcsec)
    ours["matched_with_ref"] = ours["separation_arcsec"] <= max_separation_arcsec
    return ours[ours["matched_with_ref"]]
