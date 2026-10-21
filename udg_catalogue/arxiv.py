"""Polite access to arXiv: one request at a time with jittered spacing, a pause on 429, and a full-text cache."""

from __future__ import annotations

import asyncio
import os
import random
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import TracebackType

import httpx
from sci_etl_core.extractors.async_base import AsyncExtractor
from sci_etl_core.models import ListingPage, RawRecord
from sci_etl_core.rate_limiter import AsyncRateLimiter

from udg_catalogue.progress import LoggingExtractor, Log, paper_message

ARXIV_HOST = "arxiv.org"
THROTTLE_STATUS = frozenset({429, 503})
_UNSAFE_FILE_CHARACTERS = re.compile(r"[^A-Za-z0-9._-]")


class PoliteRateLimiter(AsyncRateLimiter):
    """Let one request through at a time, each starting ``min_interval`` plus up to ``jitter`` seconds after the last.

    The gap is counted from the end of the previous request, so a slow
    download never shortens it. arXiv asks for one connection and about three
    seconds between requests; the random part keeps requests from settling
    into a fixed beat.

    :meth:`throttled` pauses every request for ``cooldown`` seconds, or longer
    when the server asks for it, and doubles the pause for each further
    throttled response, up to ``max_cooldown``. A response that is not
    throttled resets it (:meth:`observe`). Retrying requests then wait out the
    pause instead of hitting a throttled server every few seconds.
    """

    def __init__(
        self,
        min_interval: float = 3.0,
        jitter: float = 2.0,
        cooldown: float = 60.0,
        max_cooldown: float = 900.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
        uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._min_interval = min_interval
        self._jitter = jitter
        self._cooldown = cooldown
        self._max_cooldown = max_cooldown
        self._clock = clock
        self._sleep = sleep
        self._uniform = uniform
        self._lock = asyncio.Lock()
        self._next_start = 0.0
        self._throttled_in_a_row = 0

    @property
    def paused_until(self) -> float:
        """The clock reading before which no request starts."""
        return self._next_start

    async def __aenter__(self) -> PoliteRateLimiter:
        await self._lock.acquire()
        try:
            while (wait := self._next_start - self._clock()) > 0:
                await self._sleep(wait)
        except BaseException:
            self._lock.release()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        gap = self._min_interval + self._uniform(0.0, self._jitter)
        self._next_start = max(self._next_start, self._clock() + gap)
        self._lock.release()

    def throttled(self, retry_after: float | None = None) -> float:
        """Pause every request after a throttled response and return the pause, in seconds."""
        pause = min(self._cooldown * 2**self._throttled_in_a_row, self._max_cooldown)
        if retry_after is not None:
            pause = max(pause, min(retry_after, self._max_cooldown))
        self._throttled_in_a_row += 1
        self._next_start = max(self._next_start, self._clock() + pause)
        return pause

    async def observe(self, response: httpx.Response) -> None:
        """Respond to an arXiv response, as an ``httpx`` response event hook."""
        host = response.request.url.host
        if host != ARXIV_HOST and not host.endswith(f".{ARXIV_HOST}"):
            return
        if response.status_code in THROTTLE_STATUS:
            self.throttled(_seconds(response.headers.get("retry-after")))
        else:
            self._throttled_in_a_row = 0


def watch_responses(client: httpx.AsyncClient, limiter: PoliteRateLimiter) -> None:
    """Let ``limiter`` see every response ``client`` receives, so a 429 pauses all arXiv requests."""
    client.event_hooks["response"] = [*client.event_hooks["response"], limiter.observe]


def _seconds(value: str | None) -> float | None:
    try:
        seconds = float(value) if value is not None else None
    except ValueError:
        return None
    return seconds if seconds is not None and seconds >= 0 else None


class FullTextCache(AsyncExtractor):
    """Keep each paper's parsed full text in ``directory``, so it is downloaded from arXiv once.

    The cache is keyed by the versioned arXiv id, so a new version of a paper
    is downloaded again. A paper read from its abstract, because neither its
    LaTeX nor its PDF was usable, is not cached, so a later run tries the
    download again. Writes go through a temporary file, so a crash never
    leaves a partial entry. ``inner`` pages by offset, so this extractor does
    too, and ``newest_first`` runs keep working through it.
    """

    def __init__(self, inner: LoggingExtractor, directory: Path, logger: Log) -> None:
        self._inner = inner
        self._directory = directory
        self._log = logger

    def cursor_for_offset(self, offset: int) -> str:
        return self._inner.cursor_for_offset(offset)

    async def fetch_page(self, query: str, cursor: str | None, page_size: int) -> ListingPage:
        return await self._inner.fetch_page(query, cursor, page_size)

    def path_for(self, record: RawRecord) -> Path:
        return self._directory / f"{_UNSAFE_FILE_CHARACTERS.sub('_', record.record_id)}.txt"

    async def fetch_full_text(self, record: RawRecord) -> str:
        path = self.path_for(record)
        if path.is_file():
            text = await asyncio.to_thread(path.read_text, encoding="utf-8")
            self._log(paper_message(f"Full text from the cache: {len(text):,} characters"))
            return text
        text = await self._inner.fetch_full_text(record)
        if text and text != record.abstract:
            await asyncio.to_thread(_write_atomically, path, text)
        return text


def _write_atomically(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.partial")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, path)
