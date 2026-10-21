"""The query bar's chips, the status line under it and the persistent banner."""

from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass, replace

from sci_etl_core.discovery import DiscoveryResult
from sci_etl_core.search import DiscoveryGraph, QueryChip

from udg_catalogue.paper_views import describe_chip

TERM = "term"
FILTER = "filter"
DEGRADED_GLYPH = "!"
SKIPPED_GLYPH = "i"
LEG_FAILED: dict[str, str] = {
    "semantic": "semantic leg failed: the embeddings could not be queried. Showing keyword results only.",
    "lexical": "keyword leg failed: the text index could not be queried. Showing meaning results only.",
}
LEG_SKIPPED: dict[str, str] = {
    "semantic": "semantic leg skipped: the query has no whole word to embed.",
    "lexical": "keyword leg skipped: the query has nothing the text index can match.",
}
COMMUNITIES_APPROXIMATE = "communities in the graph are approximate: label propagation hit its pass limit."


@dataclass(frozen=True, slots=True)
class Chip:
    """One chip of the bar: a parsed query term, or an active filter drawn with a dashed border."""

    text: str
    kind: str = TERM
    negated: bool = False
    depth: int = 0
    title: str = ""


@dataclass(frozen=True, slots=True)
class BannerLine:
    """One condition the banner names: ``!`` for a failed leg, ``i`` for a skipped one or an approximation."""

    glyph: str
    text: str


def query_chips(chips: Sequence[QueryChip]) -> list[Chip]:
    """One chip per parsed term, negation and group depth kept as chip state rather than text."""
    return [
        Chip(
            describe_chip(replace(chip, negated=False)),
            negated=chip.negated,
            depth=chip.depth,
            title=f"NOT, {chip.operator}" if chip.negated and chip.operator else ("NOT" if chip.negated else chip.operator),
        )
        for chip in chips
    ]


def filter_chips(categories: Sequence[str] = (), years: tuple[int, int] | None = None) -> list[Chip]:
    """One dashed chip per active facet filter."""
    chips = [Chip(f"categories:{category}", FILTER, title="categories") for category in categories]
    if years is not None:
        span = str(years[0]) if years[0] == years[1] else f"{years[0]}-{years[1]}"
        chips.append(Chip(f"year:{span}", FILTER, title="year"))
    return chips


def chips_html(chips: Sequence[Chip]) -> str:
    """Render the chips as inline spans; an empty sequence renders nothing."""
    if not chips:
        return ""
    spans = []
    for chip in chips:
        classes = ["udg-chip"]
        if chip.kind == FILTER:
            classes.append("udg-chip-filter")
        if chip.negated:
            classes.append("udg-chip-negated")
        style = f' style="border-left-width:{1 + chip.depth}px"' if chip.depth else ""
        title = f' title="{html.escape(chip.title)}"' if chip.title else ""
        spans.append(f'<span class="{" ".join(classes)}"{style}{title}>{html.escape(chip.text)}</span>')
    return f'<div class="udg-chips">{"".join(spans)}</div>'


def status_line(result: DiscoveryResult, mode: str) -> str:
    """``total_matched`` and ``elapsed_ms`` for the status line; meaning-only searches count what they return."""
    if mode == "semantic":
        return f"{len(result.hits)} nearest passages · {result.elapsed_ms:.0f} ms"
    return f"{result.total_matched:,} matched · {len(result.hits)} shown · {result.elapsed_ms:.0f} ms"


def status_html(text: str) -> str:
    return f'<div class="udg-status">{html.escape(text)}</div>'


def banner_lines(result: DiscoveryResult | None, graph: DiscoveryGraph | None) -> list[BannerLine]:
    """Every condition of the current result and graph that the banner must name, failed legs first."""
    lines: list[BannerLine] = []
    if result is not None:
        for leg in result.degraded:
            lines.append(BannerLine(DEGRADED_GLYPH, LEG_FAILED.get(leg, f"{leg} leg failed: showing the other legs only.")))
        for leg in result.skipped:
            lines.append(BannerLine(SKIPPED_GLYPH, LEG_SKIPPED.get(leg, f"{leg} leg skipped: nothing to run.")))
    if graph is not None and not graph.communities_converged:
        lines.append(BannerLine(SKIPPED_GLYPH, COMMUNITIES_APPROXIMATE))
    return lines


def banner_html(lines: Sequence[BannerLine]) -> str:
    """The banner as one block, or nothing when there is nothing to report."""
    if not lines:
        return ""
    rows = "".join(
        f'<span class="udg-banner-line"><span class="udg-banner-glyph">{html.escape(line.glyph)}</span>'
        f"{html.escape(line.text)}</span>"
        for line in lines
    )
    return f'<div class="udg-banner">{rows}</div>'


def quiet_html(text: str) -> str:
    """An empty state: one sentence in the secondary colour, never an alert."""
    return f'<div class="udg-quiet">{html.escape(text)}</div>'


def region_html(text: str) -> str:
    """A region header in the mockup's style."""
    return f'<div class="udg-region">{html.escape(text)}</div>'
