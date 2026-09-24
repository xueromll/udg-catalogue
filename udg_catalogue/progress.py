"""Console progress messages: which paper is being downloaded, parsed, extracted or skipped, and why."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar

from sci_etl_core.extractors.async_base import AsyncExtractor
from sci_etl_core.llm.relevance_async import AsyncRelevanceFilter
from sci_etl_core.models import RawRecord
from sci_etl_core.observability import (
    PageFetched,
    PageFinished,
    PipelineEvent,
    RecordFinished,
    RunFinished,
    RunMetrics,
    RunStarted,
)
from sci_etl_core.parsers.base import Parser

Log = Callable[[str], None]
TITLE_WIDTH = 80

# Each record runs in its own task, so the id set when its relevance check starts
# labels every later message about that record, including ones from worker threads.
_current_paper: ContextVar[str | None] = ContextVar("current_paper", default=None)


def paper_message(message: str) -> str:
    paper = _current_paper.get()
    return message if paper is None else f"[{paper}] {message}"


def shorten(title: str, width: int = TITLE_WIDTH) -> str:
    title = " ".join(title.split())
    return title if len(title) <= width else f"{title[: width - 3]}..."


def format_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


class LoggingRelevanceFilter(AsyncRelevanceFilter):
    def __init__(self, inner: AsyncRelevanceFilter, logger: Log) -> None:
        self._inner = inner
        self._log = logger

    async def is_relevant(self, record: RawRecord) -> bool:
        _current_paper.set(record.record_id)
        self._log(paper_message(f"Checking relevance: {shorten(record.title)}"))
        return await self._inner.is_relevant(record)


class LoggingExtractor(AsyncExtractor):
    def __init__(self, inner: AsyncExtractor, logger: Log) -> None:
        self._inner = inner
        self._log = logger

    async def search(self, query: str, max_results: int, start_index: int) -> bytes | None:
        self._log(f"Fetching arXiv listing: offset {start_index}, up to {max_results} entries")
        return await self._inner.search(query, max_results, start_index)

    def parse_listing(self, raw_listing: bytes, seen_ids: set[str]) -> tuple[list[RawRecord], int]:
        return self._inner.parse_listing(raw_listing, seen_ids)

    async def fetch_full_text(self, record: RawRecord) -> str:
        self._log(paper_message("Relevant; downloading full text (LaTeX source, then PDF)"))
        text = await self._inner.fetch_full_text(record)
        if text == record.abstract:
            self._log(paper_message(f"No usable LaTeX or PDF; using the abstract ({len(text):,} characters)"))
        return text


class LoggingParser(Parser):
    def __init__(self, inner: Parser, label: str, logger: Log) -> None:
        self._inner = inner
        self._label = label
        self._log = logger

    def extract_text(self, content: bytes) -> str:
        self._log(paper_message(f"Downloaded {self._label} ({format_size(len(content))}); parsing"))
        text = self._inner.extract_text(content)
        self._log(paper_message(f"Parsed {self._label}: {len(text):,} characters"))
        return text


class PipelineEventLogger:
    def __init__(self, info: Log, warning: Log) -> None:
        self._info = info
        self._warning = warning

    def __call__(self, event: PipelineEvent) -> None:
        if isinstance(event, RunStarted):
            self._info(
                f"Run started: query {event.query!r}, offset {event.start_index}, "
                f"up to {event.total_limit} relevant papers"
            )
        elif isinstance(event, PageFetched):
            self._page_fetched(event)
        elif isinstance(event, RecordFinished):
            self._record_finished(event)
        elif isinstance(event, PageFinished):
            self._info(
                f"Page at offset {event.offset} finished in {event.duration_seconds:.1f} s; "
                f"run so far: {summarize(event.metrics)}"
            )
        elif isinstance(event, RunFinished):
            self._info(
                f"Run {event.metrics.outcome} in {event.metrics.duration_seconds:.0f} s: {summarize(event.metrics)}"
            )

    def _page_fetched(self, event: PageFetched) -> None:
        if event.entries == 0:
            self._info(f"Listing at offset {event.offset} is empty; no more papers")
            return
        already = event.entries - event.new_records
        self._info(
            f"Listing at offset {event.offset}: {event.entries} papers, {event.new_records} new, "
            f"{already} skipped as already processed"
        )

    def _record_finished(self, event: RecordFinished) -> None:
        prefix = f"[{event.record_id}] " if event.record_id else ""
        timing = f"after {event.duration_seconds:.1f} s"
        if event.outcome == "processed":
            self._info(f"{prefix}Done {timing}: {event.entities} galaxies exported")
        elif event.outcome == "irrelevant":
            self._info(f"{prefix}Skipped: judged not relevant (no new observational UDG data)")
        elif event.outcome == "deferred":
            self._info(f"{prefix}Deferred to the next run: relevant-paper limit reached")
        elif event.outcome == "failed":
            self._warning(f"{prefix}Failed {timing}, will retry next run: {event.error!r}")
        else:
            self._warning(f"Skipped: listing entry has no arXiv id ({shorten(event.title)})")


def summarize(metrics: RunMetrics) -> str:
    summary = (
        f"{metrics.pages} pages, {metrics.listed} listed, {metrics.processed} processed, "
        f"{metrics.irrelevant} irrelevant, {metrics.deferred} deferred, {metrics.failed} failed, "
        f"{metrics.skipped} without id, {metrics.entities_exported} galaxies exported"
    )
    if metrics.token_usage is not None:
        summary += f", {metrics.token_usage.total_tokens:,} LLM tokens"
    return summary
