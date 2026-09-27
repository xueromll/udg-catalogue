import asyncio

import pytest
from sci_etl_core.extractors.async_base import AsyncExtractor
from sci_etl_core.llm.relevance_async import AsyncRelevanceFilter
from sci_etl_core.models import ListingPage, RawRecord, TokenUsage
from sci_etl_core.observability import (
    PageFetched,
    PageFinished,
    RecordFinished,
    RunFinished,
    RunMetrics,
    RunStarted,
)
from sci_etl_core.parsers.base import Parser

from udg_catalogue.progress import (
    LoggingExtractor,
    LoggingParser,
    LoggingRelevanceFilter,
    PipelineEventLogger,
    format_size,
    paper_message,
    shorten,
)

RECORD = RawRecord(record_id="2601.00001v1", title="Dragonfly 44\n  revisited", abstract="Short abstract.")


class StaticRelevanceFilter(AsyncRelevanceFilter):
    async def is_relevant(self, record):
        return True


class StaticExtractor(AsyncExtractor):
    def __init__(self, full_text):
        self.full_text = full_text

    def cursor_for_offset(self, offset):
        return str(offset)

    async def fetch_page(self, query, cursor, page_size):
        return ListingPage(records=(RECORD,), entries=1, next_cursor=str(int(cursor or 0) + 1))

    async def fetch_full_text(self, record):
        return self.full_text


class UpperParser(Parser):
    def extract_text(self, content):
        return content.decode().upper()


def test_messages_carry_the_paper_id_once_its_relevance_check_starts():
    messages = []

    async def check_then_log():
        assert paper_message("before") == "before"
        assert await LoggingRelevanceFilter(StaticRelevanceFilter(), messages.append).is_relevant(RECORD)
        return paper_message("after")

    assert asyncio.run(check_then_log()) == "[2601.00001v1] after"
    assert messages == ["[2601.00001v1] Checking relevance: Dragonfly 44 revisited"]


def test_extractor_logs_listing_requests_and_downloads():
    messages = []
    extractor = LoggingExtractor(StaticExtractor("full text"), messages.append)

    assert extractor.cursor_for_offset(200) == "200"
    assert asyncio.run(extractor.fetch_page("query", "200", 100)).next_cursor == "201"
    assert asyncio.run(extractor.fetch_page("query", None, 100)).records == (RECORD,)
    assert asyncio.run(extractor.fetch_full_text(RECORD)) == "full text"
    assert messages == [
        "Fetching arXiv listing: offset 200, up to 100 entries",
        "Fetching arXiv listing: offset 0, up to 100 entries",
        "Relevant; downloading full text (LaTeX source, then PDF)",
    ]


def test_extractor_reports_falling_back_to_the_abstract():
    messages = []

    asyncio.run(LoggingExtractor(StaticExtractor(RECORD.abstract), messages.append).fetch_full_text(RECORD))

    assert messages[-1] == "No usable LaTeX or PDF; using the abstract (15 characters)"


def test_parser_logs_download_size_and_parsed_length():
    messages = []

    assert LoggingParser(UpperParser(), "PDF", messages.append).extract_text(b"abc") == "ABC"
    assert messages == ["Downloaded PDF (0 KB); parsing", "Parsed PDF: 3 characters"]


@pytest.mark.parametrize(("size", "text"), [(2048, "2 KB"), (3 * 1024 * 1024, "3.0 MB")])
def test_format_size(size, text):
    assert format_size(size) == text


def test_shorten_truncates_long_titles():
    assert shorten("a" * 100, width=10) == "aaaaaaa..."


@pytest.mark.parametrize(
    ("event", "info", "warning"),
    [
        (
            RunStarted(query="abs:udg", start_index=0, total_limit=500, newest_first=False),
            "Run started: query 'abs:udg', offset 0, up to 500 relevant papers",
            None,
        ),
        (PageFetched(offset=100, entries=0, new_records=0), "Listing at offset 100 is empty; no more papers", None),
        (
            PageFetched(offset=0, entries=100, new_records=40),
            "Listing at offset 0: 100 papers, 40 new, 60 skipped as already processed",
            None,
        ),
        (
            RecordFinished(record_id="2601.1", title="T", outcome="processed", duration_seconds=12.34, entities=3),
            "[2601.1] Done after 12.3 s: 3 galaxies exported",
            None,
        ),
        (
            RecordFinished(record_id="2601.1", title="T", outcome="irrelevant", duration_seconds=1.0),
            "[2601.1] Skipped: judged not relevant (no new observational UDG data)",
            None,
        ),
        (
            RecordFinished(record_id="2601.1", title="T", outcome="deferred", duration_seconds=0.0),
            "[2601.1] Deferred to the next run: relevant-paper limit reached",
            None,
        ),
        (
            RecordFinished(
                record_id="2601.1", title="T", outcome="failed", duration_seconds=2.0, error=RuntimeError("boom")
            ),
            None,
            "[2601.1] Failed after 2.0 s, will retry next run: RuntimeError('boom')",
        ),
        (
            RecordFinished(record_id="", title="Untitled", outcome="skipped", duration_seconds=0.0),
            None,
            "Skipped: listing entry has no arXiv id (Untitled)",
        ),
        (
            PageFinished(
                offset=0,
                duration_seconds=5.0,
                metrics=RunMetrics(pages=1, listed=2, processed=1, entities_exported=4),
            ),
            "Page at offset 0 finished in 5.0 s; run so far: 1 pages, 2 listed, 1 processed, 0 irrelevant, "
            "0 deferred, 0 failed, 0 without id, 4 galaxies exported",
            None,
        ),
        (
            RunFinished(
                metrics=RunMetrics(
                    outcome="completed",
                    duration_seconds=61.0,
                    token_usage=TokenUsage(requests=2, prompt_tokens=1000, completion_tokens=234),
                )
            ),
            "Run completed in 61 s: 0 pages, 0 listed, 0 processed, 0 irrelevant, 0 deferred, 0 failed, "
            "0 without id, 0 galaxies exported, 1,234 LLM tokens",
            None,
        ),
    ],
)
def test_event_logger_describes_each_event(event, info, warning):
    infos, warnings = [], []

    PipelineEventLogger(infos.append, warnings.append)(event)

    assert infos == ([info] if info else [])
    assert warnings == ([warning] if warning else [])
