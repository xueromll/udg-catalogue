from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

from sci_etl_core.processors import KeywordExclusionValidator, RecordValidator, ValidationResult, Violation

from udg_catalogue.config import (
    KEY_COLUMN,
    MEASUREMENT_RANGES,
    PHYSICAL_FIELDS,
    POSITION_FIELDS,
    STRICTLY_POSITIVE_FIELDS,
)

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
_NULL_LIKE_NAMES = frozenset({"null", "none", "unknown", "n/a", "nan", ""})
PAPER_LOCAL_NAME = re.compile(r"(?:(?:id|no\.?|object|source|#)\s*)?\d+", re.IGNORECASE)


class HasAnyMeasurement(RecordValidator):
    """Accept a record with a physical measurement, or with a complete sky position.

    ``ra`` or ``dec`` alone locates nothing, so neither counts on its own.
    """

    def __init__(
        self, physical_fields: Iterable[str] = PHYSICAL_FIELDS, position_fields: Iterable[str] = POSITION_FIELDS
    ) -> None:
        self._physical_fields = tuple(physical_fields)
        self._position_fields = tuple(position_fields)

    def is_valid(self, record: dict[str, Any]) -> bool:
        if any(record.get(field) is not None for field in self._physical_fields):
            return True
        return all(record.get(field) is not None for field in self._position_fields)


def _violation(code: str, field: str | None, message: str) -> ValidationResult:
    return ValidationResult(violations=(Violation(code=code, field=field, severity="error", message=message),))


class GalaxyValidator(RecordValidator):
    """Apply the catalogue rules and say which one a rejected galaxy broke.

    A galaxy is rejected when its name is missing, matches a simulation
    keyword, or only has meaning inside one paper, such as ``4692`` or
    ``ID 4692``; when a value lies outside its physical range; or when it has
    neither a physical measurement nor a complete sky position. Out-of-range
    values reject the galaxy rather than being clipped, since a value such as a
    dark-matter fraction of 96 usually means the paper was misread.
    """

    def __init__(
        self,
        simulation_keywords: Iterable[str] = SIMULATION_KEYWORDS,
        measurement_ranges: Mapping[str, tuple[float, float]] = MEASUREMENT_RANGES,
        strictly_positive_fields: Iterable[str] = STRICTLY_POSITIVE_FIELDS,
    ) -> None:
        self._keyword_validators = {
            keyword: KeywordExclusionValidator(KEY_COLUMN, [keyword]) for keyword in simulation_keywords
        }
        self._measurement_ranges = dict(measurement_ranges)
        self._strictly_positive_fields = frozenset(strictly_positive_fields)
        self._has_measurement = HasAnyMeasurement()

    def is_valid(self, record: dict[str, Any]) -> bool:
        return self.validate(record).ok

    def validate(self, record: dict[str, Any]) -> ValidationResult:
        """Return the first rule the galaxy breaks, with a code a reviewer can filter on, or no violation."""
        name = str(record.get(KEY_COLUMN, "")).strip()
        if name.lower() in _NULL_LIKE_NAMES:
            return _violation("no-name", KEY_COLUMN, "no galaxy name")
        if PAPER_LOCAL_NAME.fullmatch(name):
            return _violation(
                "paper-local-name", KEY_COLUMN, f"name {name!r} only identifies the object within its paper"
            )
        for keyword, validator in self._keyword_validators.items():
            if not validator.is_valid(record):
                return _violation("simulation-keyword", KEY_COLUMN, f"name matches simulation keyword {keyword!r}")
        for field, (low, high) in self._measurement_ranges.items():
            violation = self._range_violation(field, record.get(field), low, high)
            if violation is not None:
                return violation
        if not self._has_measurement.is_valid(record):
            return _violation(
                "no-measurement", None, "no measurements (every physical field is null and the position is incomplete)"
            )
        return ValidationResult()

    def _range_violation(self, field: str, value: Any, low: float, high: float) -> ValidationResult | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            if field in POSITION_FIELDS:
                return _violation("not-a-number", field, f"{field}={value!r} is not a number in degrees")
            return None
        if math.isnan(number):
            return None
        if field in self._strictly_positive_fields and number <= low:
            return _violation("not-positive", field, f"{field}={number:g} must be greater than {low:g}")
        if not low <= number <= high:
            return _violation("out-of-range", field, f"{field}={number:g} is outside [{low:g}, {high:g}]")
        return None


def build_galaxy_validator() -> GalaxyValidator:
    return GalaxyValidator()
