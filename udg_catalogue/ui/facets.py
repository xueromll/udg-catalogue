"""The facets sidebar: key → value (count) rows, and the selection they build filters from."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sci_etl_core.discovery import Facet

ROWS_SHOWN = 8
Selection = dict[str, tuple[str, ...]]
KEY_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


@dataclass(frozen=True, slots=True)
class FacetRow:
    key: str
    value: str
    count: int
    selected: bool = False

    @property
    def label(self) -> str:
        """``value  count`` with a thousands separator; the CSS sets it in mono and spreads the two apart."""
        return f"{self.value}  {self.count:,}"

    @property
    def widget_key(self) -> str:
        """A widget key that also serves as the CSS hook: ``facet-on-`` marks the selected row."""
        state = "on-" if self.selected else ""
        return f"facet-{state}{KEY_UNSAFE.sub('_', self.key)}-{KEY_UNSAFE.sub('_', self.value)}"


@dataclass(frozen=True, slots=True)
class FacetGroup:
    key: str
    rows: tuple[FacetRow, ...]
    hidden: int = 0


def facet_groups(facets: Sequence[Facet], selection: Mapping[str, Sequence[str]], limit: int = ROWS_SHOWN) -> list[FacetGroup]:
    """The first ``limit`` rows of each facet plus every selected row, and how many rows stay hidden."""
    groups: list[FacetGroup] = []
    for facet in facets:
        chosen = set(selection.get(facet.key, ()))
        rows = [
            FacetRow(facet.key, value, count, value in chosen)
            for position, (value, count) in enumerate(facet.counts)
            if position < limit or value in chosen
        ]
        groups.append(FacetGroup(facet.key, tuple(rows), max(0, len(facet.counts) - len(rows))))
    return groups


def toggled(selection: Mapping[str, Sequence[str]], key: str, value: str) -> Selection:
    """The selection with ``value`` added to or removed from ``key``; keys without values disappear."""
    values = set(selection.get(key, ()))
    values ^= {value}
    result: Selection = {name: tuple(sorted(chosen)) for name, chosen in selection.items() if name != key and chosen}
    if values:
        result[key] = tuple(sorted(values))
    return result


def selection_filters(selection: Mapping[str, Sequence[str]]) -> tuple[tuple[str, ...], tuple[int, int] | None]:
    """The ``(categories, years)`` pair ``paper_filters`` takes; years span the chosen year values."""
    categories = tuple(sorted(selection.get("categories", ())))
    years = sorted(int(year) for year in selection.get("year", ()) if year.isdecimal())
    return categories, ((years[0], years[-1]) if years else None)


def overview_facets(categories: Sequence[tuple[str, int]]) -> list[Facet]:
    """The facets shown before any search: the whole index's category counts."""
    return [Facet("categories", tuple(categories))]
