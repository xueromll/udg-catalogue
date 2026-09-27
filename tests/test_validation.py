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


def test_a_physical_measurement_or_a_complete_position_counts_as_a_measurement():
    validator = HasAnyMeasurement()

    assert validator.is_valid({"distance_mpc": 1.0})
    assert validator.is_valid({"ra": 10.0, "dec": 0.0})
    assert not validator.is_valid({"ra": 10.0})
    assert not validator.is_valid({"dec": 0.0, "distance_mpc": None})


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        ({"galaxy_name": "Dragonfly 44", "ra": 10.0, "dec": 1.0}, None),
        ({"galaxy_name": "Dragonfly 44", "distance_mpc": 100.0, "dark_matter_fraction": 0.0}, None),
        ({"galaxy_name": "DF 44", "ra": 10.0, "dec": 1.0, "stellar_mass_solar": "3.2 ± 0.4"}, None),
        ({"galaxy_name": "DF 44", "ra": 10.0, "dec": 1.0, "stellar_mass_solar": float("nan")}, None),
        ({"galaxy_name": " n/a ", "ra": 10.0}, "no galaxy name"),
        ({"ra": 10.0}, "no galaxy name"),
        ({"galaxy_name": "4692", "ra": 10.0, "dec": 1.0}, "name '4692' only identifies the object within its paper"),
        ({"galaxy_name": "ID 4692", "ra": 10.0}, "name 'ID 4692' only identifies the object within its paper"),
        ({"galaxy_name": "No. 12", "ra": 10.0}, "name 'No. 12' only identifies the object within its paper"),
        ({"galaxy_name": "# 5", "ra": 10.0}, "name '# 5' only identifies the object within its paper"),
        ({"galaxy_name": "source 7", "ra": 10.0}, "name 'source 7' only identifies the object within its paper"),
        ({"galaxy_name": "TNG50-1", "ra": 10.0}, "name matches simulation keyword 'tng'"),
        ({"galaxy_name": "DF 3", "ra": "02h41m46.8s"}, "ra='02h41m46.8s' is not a number in degrees"),
        ({"galaxy_name": "DF 2", "ra": 10.0, "dec": -100.5}, "dec=-100.5 is outside [-90, 90]"),
        ({"galaxy_name": "DF 44", "dark_matter_fraction": 96}, "dark_matter_fraction=96 is outside [0, 1]"),
        ({"galaxy_name": "DF 44", "distance_mpc": -5.0}, "distance_mpc=-5 must be greater than 0"),
        ({"galaxy_name": "DF 44", "effective_radius_kpc": 0}, "effective_radius_kpc=0 must be greater than 0"),
        ({"galaxy_name": "Abell 1697", "stellar_mass_solar": 1.32e13}, "stellar_mass_solar=1.32e+13 is outside [0, 1e+12]"),
        ({"galaxy_name": "DF 44", "effective_radius_kpc": 250.0}, "effective_radius_kpc=250 is outside [0, 100]"),
        (
            {"galaxy_name": "WLM", "ra": 10.0, "distance_mpc": None},
            "no measurements (every physical field is null and the position is incomplete)",
        ),
    ],
)
def test_galaxy_validator_explains_rejections(record, reason):
    result = build_galaxy_validator().validate(record)

    assert [violation.message for violation in result.violations] == ([] if reason is None else [reason])
    assert all(violation.severity == "error" for violation in result.violations)


@pytest.mark.parametrize(
    ("record", "code", "field"),
    [
        ({"galaxy_name": "null", "ra": 10.0}, "no-name", "galaxy_name"),
        ({"galaxy_name": "ID 4692", "ra": 10.0}, "paper-local-name", "galaxy_name"),
        ({"galaxy_name": "mock_1", "ra": 10.0}, "simulation-keyword", "galaxy_name"),
        ({"galaxy_name": "DF 3", "dec": "north"}, "not-a-number", "dec"),
        ({"galaxy_name": "DF 44", "distance_mpc": 0}, "not-positive", "distance_mpc"),
        ({"galaxy_name": "DF 44", "dark_matter_fraction": 2}, "out-of-range", "dark_matter_fraction"),
        ({"galaxy_name": "DF 44"}, "no-measurement", None),
    ],
)
def test_each_rejection_carries_a_code_and_the_field_it_concerns(record, code, field):
    (violation,) = build_galaxy_validator().validate(record).violations

    assert (violation.code, violation.field) == (code, field)
