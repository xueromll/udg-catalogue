from __future__ import annotations

import os
from collections.abc import Callable
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
    TableLayoutStep,
)

from udg_catalogue.astrometry import (
    UNKNOWN_CONSTELLATION,
    CartesianDistanceFeatures,
    ConstellationStep,
    SkyPositionMatcher,
)
from udg_catalogue.config import KEY_COLUMN, MEASUREMENT_FIELDS, CatalogueConfig
from udg_catalogue.naming import GalaxyNameNormalizer

NORMALIZED_KEY_COLUMN = "_norm_key"
INTERNAL_COLUMN_PREFIX = "_"
RECORD_COLUMN = "record_id"
EXTRA_COLUMN = "extra"
SOURCE_PAPERS_COLUMN = "source_papers"
LEADING_COLUMNS: tuple[str, ...] = (
    KEY_COLUMN,
    "completeness_pct",
    "quality_flag",
    "constellation",
    "cluster_id",
    SOURCE_PAPERS_COLUMN,
)
SORT_ORDER: tuple[tuple[str, bool], ...] = (
    ("completeness_pct", False),
    ("constellation", True),
    ("cluster_id", True),
    (KEY_COLUMN, True),
)


def build_catalogue_layout() -> TableLayoutStep:
    return TableLayoutStep(
        sort_by=SORT_ORDER,
        leading_columns=LEADING_COLUMNS,
        hidden_prefixes=(INTERNAL_COLUMN_PREFIX,),
    )


class RawRowsStep(Processor):
    """Prepare the raw catalogue's rows, one per galaxy a paper reports, for merging.

    The arXiv id and the ``extra`` column become internal columns, which the
    layout step hides, and each measurement is read as a number: a value the
    paper gave as text, such as ``"3.2 +/- 0.4"``, becomes empty here and
    stays readable in the raw catalogue.
    """

    def process(self, frame: pd.DataFrame) -> pd.DataFrame:
        prepared = frame.rename(
            columns={
                RECORD_COLUMN: INTERNAL_COLUMN_PREFIX + RECORD_COLUMN,
                EXTRA_COLUMN: INTERNAL_COLUMN_PREFIX + EXTRA_COLUMN,
            }
        )
        for field in MEASUREMENT_FIELDS:
            if field in prepared.columns:
                prepared[field] = pd.to_numeric(prepared[field], errors="coerce")
        return prepared


def build_catalogue_chain(config: CatalogueConfig, normalizer: KeyNormalizer | None = None) -> ProcessorChain:
    """Merge the raw rows into one row per galaxy, listing the papers each galaxy's rows came from."""
    return ProcessorChain(
        [
            RawRowsStep(),
            NormalizationStep(KEY_COLUMN, normalizer or GalaxyNameNormalizer(), NORMALIZED_KEY_COLUMN),
            DeduplicationStep(
                NORMALIZED_KEY_COLUMN,
                matcher=SkyPositionMatcher(),
                match_threshold=config.deduplication.max_separation_arcsec,
                source_column=INTERNAL_COLUMN_PREFIX + RECORD_COLUMN,
                sources_column=SOURCE_PAPERS_COLUMN,
            ),
            CompletenessStep(list(MEASUREMENT_FIELDS)),
            ConstellationStep(),
            ClusteringStep(
                CartesianDistanceFeatures(),
                eps=config.clustering.max_distance_mpc,
                min_samples=config.clustering.min_samples,
            ),
            QualityFlagStep(),
            build_catalogue_layout(),
        ]
    )


def read_catalogue(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        dtype={KEY_COLUMN: str, RECORD_COLUMN: str, SOURCE_PAPERS_COLUMN: str},
        keep_default_na=False,
        na_values=[""],
    )


def read_optional_catalogue(path: Path) -> pd.DataFrame:
    if not path.is_file() or path.stat().st_size == 0:
        return pd.DataFrame()
    return read_catalogue(path)


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
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f"{destination.name}.tmp")
    catalogue.to_csv(staging, index=False, encoding="utf-8")
    os.replace(staging, destination)


def build_sorted_catalogue(
    config: CatalogueConfig,
    log: Callable[[str], None],
    normalizer: KeyNormalizer | None = None,
    *,
    replace: bool = False,
) -> pd.DataFrame | None:
    """Build the sorted catalogue from the raw catalogue alone and write it.

    The published catalogue is never read back as input, so a rebuild with
    corrected rules may merge or drop rows. A raw catalogue with fewer rows than
    the published catalogue has galaxies cannot have produced it, which usually
    means the raw data is incomplete, such as in a fresh clone; the published
    file is then kept unless ``replace`` is set, as after a rebuild from
    scratch.
    """
    source = config.paths.raw_catalogue
    destination = config.paths.sorted_catalogue
    if not source.is_file() or source.stat().st_size == 0:
        log(f"Raw catalogue not found or empty: {source}")
        return None
    raw = read_catalogue(source)
    if raw.empty:
        log(f"Raw catalogue has no rows: {source}")
        return None
    if RECORD_COLUMN not in raw.columns:
        log(
            f"Raw catalogue has no {RECORD_COLUMN} column: {source} was written before rows named their paper; "
            "rebuild it with --rescan"
        )
        return None
    existing = read_optional_catalogue(destination)
    if len(raw) < len(existing) and not replace:
        log(
            f"Refusing to overwrite {destination}: the raw catalogue has {len(raw)} rows but the published "
            f"one has {len(existing)} galaxies, so the raw data looks incomplete. "
            "Pass --replace-catalogue to build the catalogue from the raw rows alone."
        )
        return existing
    catalogue = build_catalogue_chain(config, normalizer).process(raw)
    write_catalogue(catalogue, destination)
    for line in describe_catalogue(catalogue):
        log(line)
    log(f"Sorted catalogue written to {destination}")
    return catalogue
