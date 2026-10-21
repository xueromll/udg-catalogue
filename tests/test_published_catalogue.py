"""Checks on the committed catalogue, ``data/udg_database_sorted.csv``, as published.

A check the published catalogue does not pass yet carries a strict expected
failure marker: once a rebuild passes the check, the suite fails until its
marker is removed.
"""

import astropy.units as u
import pandas as pd
import pytest

from udg_catalogue.astrometry import located_rows, sky_coordinates
from udg_catalogue.config import DEFAULT_CONFIG_PATH, KEY_COLUMN, MEASUREMENT_FIELDS, load_catalogue_config
from udg_catalogue.postprocess import read_catalogue
from udg_catalogue.validation import PAPER_LOCAL_NAME, build_galaxy_validator

NOT_PASSED_YET = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="the catalogue rebuilt on 2026-10-21 does not pass this rule yet; the next rebuild must pass it",
)


@pytest.fixture(scope="module")
def published() -> pd.DataFrame:
    config = load_catalogue_config(DEFAULT_CONFIG_PATH)
    return read_catalogue(config.paths.sorted_catalogue)


@pytest.fixture(scope="module")
def matching_radius_arcsec() -> float:
    return load_catalogue_config(DEFAULT_CONFIG_PATH).deduplication.max_separation_arcsec


def test_the_published_catalogue_has_the_catalogue_columns(published):
    assert {KEY_COLUMN, *MEASUREMENT_FIELDS} <= set(published.columns)
    assert len(published) > 0


def test_no_two_published_galaxies_lie_within_the_matching_radius(published, matching_radius_arcsec):
    located = published[located_rows(published)]
    coordinates = sky_coordinates(located)
    first, second, _, _ = coordinates.search_around_sky(coordinates, matching_radius_arcsec * u.arcsec)
    names = located[KEY_COLUMN].to_numpy()
    close_pairs = sorted({(names[a], names[b]) for a, b in zip(first, second, strict=True) if a < b})
    assert close_pairs == []


def test_no_published_name_only_identifies_a_galaxy_within_its_paper(published):
    names = published[KEY_COLUMN].astype(str).str.strip()
    assert sorted(names[names.map(lambda name: PAPER_LOCAL_NAME.fullmatch(name) is not None)]) == []


def test_every_published_galaxy_passes_the_extraction_rules(published):
    validator = build_galaxy_validator()
    rejected = {}
    for record in published[[KEY_COLUMN, *MEASUREMENT_FIELDS]].to_dict("records"):
        values = {field: None if pd.isna(value) else value for field, value in record.items()}
        result = validator.validate(values)
        if not result.ok:
            rejected[record[KEY_COLUMN]] = [violation.code for violation in result.violations]
    assert rejected == {}


@NOT_PASSED_YET
def test_no_published_dark_matter_fraction_sits_on_a_bound(published):
    fractions = pd.to_numeric(published["dark_matter_fraction"], errors="coerce")
    at_bound = published.loc[fractions.isin([0.0, 1.0]), KEY_COLUMN]
    assert sorted(at_bound) == []
