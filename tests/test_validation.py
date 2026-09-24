import pytest

from udg_catalogue.validation import HasAnyMeasurement, build_galaxy_validator


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"galaxy_name": "Dragonfly 44", "ra": 10.0, "dec": -10.0}, True),
        ({"galaxy_name": "Firefly 7", "distance_mpc": 20.0}, True),
        ({"galaxy_name": "illustris_galaxy_1", "ra": 10.0}, False),
        ({"galaxy_name": "mock_catalog_obj", "ra": 10.0}, False),
        ({"galaxy_name": "TNG50-1", "distance_mpc": 20.0}, False),
        ({"galaxy_name": "DF 1", "ra": 400.0, "dec": 0.0}, False),
        ({"galaxy_name": "DF 2", "ra": 10.0, "dec": -100.0}, False),
        ({"galaxy_name": "DF 3", "ra": "invalid", "dec": 0.0}, False),
        ({"galaxy_name": "DF 4", "ra": 10.0, "dec": "invalid"}, False),
        ({"galaxy_name": "NaN", "ra": 10.0}, False),
        ({"galaxy_name": None, "ra": 10.0}, False),
        ({"galaxy_name": "ValidName"}, False),
        ({}, False),
    ],
)
def test_galaxy_validator_applies_the_catalogue_rules(record, expected):
    assert build_galaxy_validator().is_valid(record) is expected


def test_has_any_measurement_ignores_missing_values():
    validator = HasAnyMeasurement(["ra", "dec"])

    assert validator.is_valid({"dec": 0.0})
    assert not validator.is_valid({"ra": None, "distance_mpc": 1.0})
