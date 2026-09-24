from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sci_etl_core import AsyncEntityExtractor
from sci_etl_core.processors import (
    CompositeValidator,
    KeywordExclusionValidator,
    NumericRangeValidator,
    RecordValidator,
)

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


class ValidatedEntityExtractor(AsyncEntityExtractor):
    def __init__(
        self,
        inner: AsyncEntityExtractor,
        validator: RecordValidator,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self._inner = inner
        self._validator = validator
        self._log = logger or (lambda _message: None)

    async def extract(self, text: str | bytes) -> list[dict[str, Any]]:
        accepted: list[dict[str, Any]] = []
        for entity in await self._inner.extract(text):
            if self._validator.is_valid(entity):
                accepted.append(entity)
            else:
                self._log(f"Entity rejected by validation: {entity.get(KEY_COLUMN)!r}")
        return accepted


def build_galaxy_validator() -> GalaxyValidator:
    return GalaxyValidator()
