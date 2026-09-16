import asyncio

import pytest
from sci_etl_core import AsyncEntityExtractor

from udg_catalogue.validation import HasAnyMeasurement, ValidatedEntityExtractor, build_galaxy_validator


class StaticEntityExtractor(AsyncEntityExtractor):
    def __init__(self, entities):
        self._entities = entities
        self.texts = []

    async def extract(self, text):
        self.texts.append(text)
        return self._entities


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


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        ({"galaxy_name": "Dragonfly 44", "ra": 10.0}, None),
        ({"galaxy_name": " n/a ", "ra": 10.0}, "no galaxy name"),
        ({"ra": 10.0}, "no galaxy name"),
        ({"galaxy_name": "TNG50-1", "ra": 10.0}, "name matches simulation keyword 'tng'"),
        ({"galaxy_name": "DF 3", "ra": "02h41m46.8s"}, "ra='02h41m46.8s' is not a number in degrees"),
        ({"galaxy_name": "DF 2", "ra": 10.0, "dec": -100.5}, "dec=-100.5 is outside [-90, 90]"),
        ({"galaxy_name": "WLM", "ra": None, "distance_mpc": None}, "no measurements (every numeric field is null)"),
    ],
)
def test_galaxy_validator_explains_rejections(record, reason):
    assert build_galaxy_validator().rejection_reason(record) == reason


def test_validated_extractor_drops_and_logs_rejected_entities():
    messages = []
    inner = StaticEntityExtractor(
        [{"galaxy_name": "DF 44", "ra": 1.0}, {"galaxy_name": "mock_1", "ra": 1.0}]
    )
    extractor = ValidatedEntityExtractor(inner, build_galaxy_validator(), logger=messages.append)

    assert asyncio.run(extractor.extract("paper text")) == [{"galaxy_name": "DF 44", "ra": 1.0}]
    assert inner.texts == ["paper text"]
    assert messages == [
        "Extracting galaxies with the LLM from 10 characters",
        "Rejected galaxy 'mock_1': name matches simulation keyword 'mock'",
        "LLM returned 2 galaxies: 1 accepted, 1 rejected",
    ]


def test_validated_extractor_without_logger_drops_silently():
    extractor = ValidatedEntityExtractor(
        StaticEntityExtractor([{"galaxy_name": "mock_1", "ra": 1.0}]),
        build_galaxy_validator(),
    )

    assert asyncio.run(extractor.extract("paper text")) == []
