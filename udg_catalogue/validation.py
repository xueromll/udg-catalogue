from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sci_etl_core.processors import (
    CompositeValidator,
    KeywordExclusionValidator,
    NumericRangeValidator,
    RecordValidator,
)

from udg_catalogue.config import KEY_COLUMN, MEASUREMENT_FIELDS

SIMULATION_KEYWORDS: tuple[str, ...] = (
    "sim",
    "simulation",
    "mock",
    "synthetic",
    "toy",
    "model",
    "tng",
    "illustris",
    "fire",
    "eagle",
    "romulus",
    "nihao",
    "gadget",
    "gizmo",
    "subhalo",
    "test",
    "example",
    "idealized",
    "artific",
)
SKY_COORDINATE_RANGES: dict[str, tuple[float, float]] = {"ra": (0.0, 360.0), "dec": (-90.0, 90.0)}


class HasAnyMeasurement(RecordValidator):
    def __init__(self, fields: Iterable[str]) -> None:
        self._fields = tuple(fields)

    def is_valid(self, record: dict[str, Any]) -> bool:
        return any(record.get(field) is not None for field in self._fields)


def build_galaxy_validator() -> RecordValidator:
    return CompositeValidator(
        [
            KeywordExclusionValidator(KEY_COLUMN, list(SIMULATION_KEYWORDS)),
            NumericRangeValidator(SKY_COORDINATE_RANGES),
            HasAnyMeasurement(MEASUREMENT_FIELDS),
        ]
    )
