from __future__ import annotations

from collections.abc import Sequence
from typing import Any

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
    """Group located rows that lie within ``threshold`` arcseconds of each other.

    Every pair within the threshold joins one group, so exact duplicates and
    groups of three or more rows are found, and a chain of close rows forms a
    single group. Each group is returned as pairs of its lowest row label with
    every other member, so deduplication keeps that row and fills its gaps from
    the others.
    """

    def __init__(self, ra_column: str = "ra", dec_column: str = "dec") -> None:
        self._ra_column = ra_column
        self._dec_column = dec_column

    def find_matches(self, frame: pd.DataFrame, threshold: float) -> list[tuple[int, int]]:
        located = frame[located_rows(frame, self._ra_column, self._dec_column)]
        if len(located) < 2:
            return []
        coordinates = sky_coordinates(located, self._ra_column, self._dec_column)
        first, second, _, _ = coordinates.search_around_sky(coordinates, threshold * u.arcsec)
        labels = [int(label) for label in located.index]
        groups = _Groups(labels)
        for position, neighbour in zip(first, second, strict=True):
            groups.join(labels[position], labels[neighbour])
        return sorted((groups.root(label), label) for label in labels if groups.root(label) != label)


class _Groups:
    def __init__(self, members: Sequence[int]) -> None:
        self._parent = {member: member for member in members}

    def root(self, member: int) -> int:
        while self._parent[member] != member:
            self._parent[member] = self._parent[self._parent[member]]
            member = self._parent[member]
        return member

    def join(self, first: int, second: int) -> None:
        first_root, second_root = self.root(first), self.root(second)
        if first_root != second_root:
            self._parent[max(first_root, second_root)] = min(first_root, second_root)


class NamesakeSplitStep(Processor):
    """Keep apart galaxies that share a name key but not a place on the sky.

    Papers on different fields reuse field-local names such as ``UDG 5``, so
    the rows of one key are split into one galaxy per sky position: a located
    row joins a galaxy when it lies within ``max_separation_arcmin`` of one of
    its rows. A key whose located rows all lie together, or that has none, is
    left whole, since papers disagreeing on a distance, as on the 13 or 20 Mpc
    of NGC 1052-DF2, are no sign of two galaxies.

    When a key names galaxies in several places, a row without a position joins
    the one whose median distance agrees with its own within a factor of
    ``max_distance_ratio``, the closest when several agree. When none agrees
    and exactly one galaxy has no distance, the row joins that one. The rows
    that cannot be placed, with no distance or with one no galaxy fits, are
    kept together, apart from the rest.

    Every galaxy after the one holding the key's first row gets the key with a
    ``#n`` suffix, so deduplication merges rows within a galaxy only.
    """

    def __init__(
        self,
        key_column: str,
        max_separation_arcmin: float = 10.0,
        max_distance_ratio: float = 1.5,
        distance_column: str = "distance_mpc",
        ra_column: str = "ra",
        dec_column: str = "dec",
    ) -> None:
        self._key_column = key_column
        self._max_separation = max_separation_arcmin * u.arcmin
        self._max_log_ratio = float(np.log(max_distance_ratio))
        self._distance_column = distance_column
        self._ra_column = ra_column
        self._dec_column = dec_column

    def process(self, frame: pd.DataFrame) -> pd.DataFrame:
        keys = frame[self._key_column]
        repeated = keys[(keys != "") & keys.duplicated(keep=False)]
        if repeated.empty:
            return frame
        located = located_rows(frame, self._ra_column, self._dec_column)
        if self._distance_column in frame.columns:
            distance = pd.to_numeric(frame[self._distance_column], errors="coerce")
        else:
            distance = pd.Series(np.nan, index=frame.index)
        distance = distance.where(distance > 0)
        split = keys.copy()
        for key, members in repeated.groupby(repeated, sort=False).groups.items():
            galaxies = self._galaxies(frame.loc[members], located[members], distance[members])
            for number, galaxy in enumerate(sorted(galaxies, key=min)[1:], start=1):
                split[galaxy] = f"{key}#{number}"
        if split.equals(keys):
            return frame
        frame = frame.copy()
        frame[self._key_column] = split
        return frame

    def _galaxies(self, rows: pd.DataFrame, located: pd.Series, distance: pd.Series) -> list[list[Any]]:
        galaxies = self._by_position(rows[located])
        if len(galaxies) < 2:
            return [list(rows.index)]
        medians = [distance[galaxy].median() for galaxy in galaxies]
        undistanced = [index for index, median in enumerate(medians) if pd.isna(median)]
        unplaced: list[Any] = []
        for label in rows.index[~located]:
            target = self._agreeing_galaxy(distance[label], medians, undistanced)
            if target is None:
                unplaced.append(label)
            else:
                galaxies[target].append(label)
        return [*galaxies, unplaced] if unplaced else galaxies

    def _agreeing_galaxy(self, own: float, medians: list[float], undistanced: list[int]) -> int | None:
        if pd.isna(own):
            return None
        gaps = [
            (abs(np.log(own) - np.log(median)), index) for index, median in enumerate(medians) if pd.notna(median)
        ]
        agreeing = [gap for gap in gaps if gap[0] <= self._max_log_ratio]
        if agreeing:
            return min(agreeing)[1]
        return undistanced[0] if len(undistanced) == 1 else None

    def _by_position(self, rows: pd.DataFrame) -> list[list[Any]]:
        labels = list(rows.index)
        if len(labels) < 2:
            return [labels]
        coordinates = sky_coordinates(rows, self._ra_column, self._dec_column)
        first, second, _, _ = coordinates.search_around_sky(coordinates, self._max_separation)
        positions = _Groups(range(len(labels)))
        for position, neighbour in zip(first, second, strict=True):
            positions.join(int(position), int(neighbour))
        galaxies: dict[int, list[Any]] = {}
        for position, label in enumerate(labels):
            galaxies.setdefault(positions.root(position), []).append(label)
        return list(galaxies.values())


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
