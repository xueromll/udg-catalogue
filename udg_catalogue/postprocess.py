from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path

import pandas as pd
from sci_etl_core.processors import (
    ClusteringStep,
    CompletenessStep,
    DeduplicationStep,
    KeyNormalizer,
    NormalizationStep,
    Processor,
    ProcessorChain,
    QualityFlagStep,
)

from udg_catalogue.astrometry import (
    UNKNOWN_CONSTELLATION,
    CartesianDistanceFeatures,
    ConstellationStep,
    SkyPositionMatcher,
)
from udg_catalogue.config import FRACTION_BOUNDS, KEY_COLUMN, MEASUREMENT_FIELDS, CatalogueConfig
from udg_catalogue.naming import GalaxyNameNormalizer

NORMALIZED_KEY_COLUMN = "_norm_key"
LEADING_COLUMNS: tuple[str, ...] = (
    KEY_COLUMN,
    "completeness_pct",
    "quality_flag",
    "constellation",
    "cluster_id",
)
SORT_ORDER: tuple[tuple[str, bool], ...] = (
    ("completeness_pct", False),
    ("constellation", True),
    ("cluster_id", True),
    (KEY_COLUMN, True),
)


class ValueClipStep(Processor):
    def __init__(self, bounds: Mapping[str, tuple[float, float]]) -> None:
        self._bounds = dict(bounds)

    def process(self, frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        for column, (low, high) in self._bounds.items():
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce").clip(low, high)
        return frame


class CatalogueLayoutStep(Processor):
    def process(self, frame: pd.DataFrame) -> pd.DataFrame:
        sort_keys = [(column, ascending) for column, ascending in SORT_ORDER if column in frame.columns]
        if sort_keys:
            frame = frame.sort_values(
                by=[column for column, _ in sort_keys],
                ascending=[ascending for _, ascending in sort_keys],
            )
        public = [column for column in frame.columns if not column.startswith("_")]
        leading = [column for column in LEADING_COLUMNS if column in public]
        return frame[leading + [column for column in public if column not in leading]]


def build_catalogue_chain(config: CatalogueConfig, normalizer: KeyNormalizer | None = None) -> ProcessorChain:
    return ProcessorChain(
        [
            NormalizationStep(KEY_COLUMN, normalizer or GalaxyNameNormalizer(), NORMALIZED_KEY_COLUMN),
            DeduplicationStep(
                NORMALIZED_KEY_COLUMN,
                matcher=SkyPositionMatcher(),
                match_threshold=config.deduplication.max_separation_arcsec,
            ),
            ValueClipStep(FRACTION_BOUNDS),
            CompletenessStep(list(MEASUREMENT_FIELDS)),
            ConstellationStep(),
            ClusteringStep(
                CartesianDistanceFeatures(),
                eps=config.clustering.max_distance_mpc,
                min_samples=config.clustering.min_samples,
            ),
            QualityFlagStep(),
            CatalogueLayoutStep(),
        ]
    )


def read_catalogue(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={KEY_COLUMN: str}, keep_default_na=False, na_values=[""])


def describe_catalogue(catalogue: pd.DataFrame) -> list[str]:
    known_constellations = catalogue.loc[catalogue["constellation"] != UNKNOWN_CONSTELLATION, "constellation"]
    clustered = catalogue.loc[catalogue["cluster_id"] != -1, "cluster_id"]
    return [
        f"Galaxies in sorted catalogue: {len(catalogue)}",
        f"Galaxies with 100% completeness: {int((catalogue['completeness_pct'] == 100).sum())}",
        f"Constellations represented: {known_constellations.nunique()}",
        f"3D clusters: {clustered.nunique()}",
    ]


def write_catalogue(catalogue: pd.DataFrame, destination: Path) -> None:
    staging = destination.with_name(f"{destination.name}.tmp")
    catalogue.to_csv(staging, index=False, encoding="utf-8")
    os.replace(staging, destination)


def build_sorted_catalogue(
    config: CatalogueConfig,
    log: Callable[[str], None],
    normalizer: KeyNormalizer | None = None,
) -> pd.DataFrame | None:
    source = config.paths.raw_catalogue
    if not source.is_file() or source.stat().st_size == 0:
        log(f"Raw catalogue not found or empty: {source}")
        return None
    raw = read_catalogue(source)
    if raw.empty:
        log(f"Raw catalogue has no rows: {source}")
        return None
    catalogue = build_catalogue_chain(config, normalizer).process(raw)
    write_catalogue(catalogue, config.paths.sorted_catalogue)
    for line in describe_catalogue(catalogue):
        log(line)
    log(f"Sorted catalogue written to {config.paths.sorted_catalogue}")
    return catalogue
