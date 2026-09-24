from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from sci_etl_core import AsyncEntityExtractor
from sci_etl_core.processors import KeywordExclusionValidator, RecordValidator

from udg_catalogue.config import KEY_COLUMN, MEASUREMENT_FIELDS
from udg_catalogue.progress import paper_message

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
_NULL_LIKE_NAMES = frozenset({"null", "none", "unknown", "n/a", "nan", ""})


class HasAnyMeasurement(RecordValidator):
    def __init__(self, fields: Iterable[str]) -> None:
        self._fields = tuple(fields)

    def is_valid(self, record: dict[str, Any]) -> bool:
        return any(record.get(field) is not None for field in self._fields)


class GalaxyValidator(RecordValidator):
    """Apply the catalogue rules and say which one a rejected galaxy broke."""

    def __init__(
        self,
        simulation_keywords: Iterable[str] = SIMULATION_KEYWORDS,
        coordinate_ranges: dict[str, tuple[float, float]] = SKY_COORDINATE_RANGES,
        measurement_fields: Iterable[str] = MEASUREMENT_FIELDS,
    ) -> None:
        self._keyword_validators = {
            keyword: KeywordExclusionValidator(KEY_COLUMN, [keyword]) for keyword in simulation_keywords
        }
        self._coordinate_ranges = coordinate_ranges
        self._has_measurement = HasAnyMeasurement(measurement_fields)

    def is_valid(self, record: dict[str, Any]) -> bool:
        return self.rejection_reason(record) is None

    def rejection_reason(self, record: dict[str, Any]) -> str | None:
        if str(record.get(KEY_COLUMN, "")).strip().lower() in _NULL_LIKE_NAMES:
            return "no galaxy name"
        for keyword, validator in self._keyword_validators.items():
            if not validator.is_valid(record):
                return f"name matches simulation keyword {keyword!r}"
        for field, (low, high) in self._coordinate_ranges.items():
            value = record.get(field)
            if value is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                return f"{field}={value!r} is not a number in degrees"
            if not low <= number <= high:
                return f"{field}={number:g} is outside [{low:g}, {high:g}]"
        if not self._has_measurement.is_valid(record):
            return "no measurements (every numeric field is null)"
        return None


class ValidatedEntityExtractor(AsyncEntityExtractor):
    def __init__(
        self,
        inner: AsyncEntityExtractor,
        validator: GalaxyValidator,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self._inner = inner
        self._validator = validator
        self._log = logger or (lambda _message: None)

    async def extract(self, text: str | bytes) -> list[dict[str, Any]]:
        self._log(paper_message(f"Extracting galaxies with the LLM from {len(text):,} characters"))
        entities = await self._inner.extract(text)
        accepted: list[dict[str, Any]] = []
        for entity in entities:
            reason = self._validator.rejection_reason(entity)
            if reason is None:
                accepted.append(entity)
            else:
                self._log(paper_message(f"Rejected galaxy {entity.get(KEY_COLUMN)!r}: {reason}"))
        self._log(
            paper_message(
                f"LLM returned {len(entities)} galaxies: {len(accepted)} accepted, "
                f"{len(entities) - len(accepted)} rejected"
            )
        )
        return accepted


def build_galaxy_validator() -> GalaxyValidator:
    return GalaxyValidator()
