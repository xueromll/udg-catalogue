import asyncio

import httpx
import pytest
from sci_etl_core.models import ListingPage, RawRecord

from udg_catalogue.arxiv import FullTextCache, PoliteRateLimiter, watch_responses

RECORD = RawRecord(record_id="2401.00001v2", title="A UDG", abstract="An abstract.", source_url="https://arxiv.org/abs/2401.00001v2")


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.slept = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def limiter(clock, **settings):
    return PoliteRateLimiter(clock=clock, sleep=clock.sleep, uniform=lambda low, high: high, **settings)


async def requests(polite, clock, count, duration=0.0):
    starts = []
    for _ in range(count):
        async with polite:
            starts.append(clock.now)
            clock.now += duration
    return starts


def test_requests_start_the_interval_and_jitter_after_the_previous_one_ended():
    clock = FakeClock()
    polite = limiter(clock, min_interval=3.0, jitter=2.0)

    assert asyncio.run(requests(polite, clock, 3, duration=10.0)) == [100.0, 115.0, 130.0]


def test_only_one_request_runs_at_a_time():
    clock = FakeClock()
    polite = limiter(clock, min_interval=0.0, jitter=0.0)
    running, peak = 0, 0

    async def request():
        nonlocal running, peak
        async with polite:
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0)
            running -= 1

    async def main():
        await asyncio.gather(*(request() for _ in range(5)))

    asyncio.run(main())
    assert peak == 1


def test_a_throttled_response_pauses_every_request_and_the_pause_doubles_until_a_success():
    clock = FakeClock()
    polite = limiter(clock, min_interval=0.0, jitter=0.0, cooldown=60.0, max_cooldown=200.0)

    assert [polite.throttled() for _ in range(3)] == [60.0, 120.0, 200.0]
    assert polite.paused_until == 300.0
    assert asyncio.run(requests(polite, clock, 1)) == [300.0]
    assert polite.throttled(retry_after=500.0) == 200.0
    assert polite.throttled(retry_after=1.0) == 200.0


def response(status, url="https://export.arxiv.org/api/query", headers=None):
    return httpx.Response(status, headers=headers, request=httpx.Request("GET", url))


def test_observe_pauses_on_arxiv_throttling_honours_retry_after_and_resets_on_success():
    clock = FakeClock()
    polite = limiter(clock, cooldown=60.0, max_cooldown=900.0)

    asyncio.run(polite.observe(response(429, headers={"Retry-After": "120"})))
    assert polite.paused_until == 220.0
    asyncio.run(polite.observe(response(503, url="https://arxiv.org/e-print/2401.00001", headers={"Retry-After": "soon"})))
    assert polite.paused_until == 220.0
    asyncio.run(polite.observe(response(200)))
    asyncio.run(polite.observe(response(429, headers={"Retry-After": "-5"})))
    assert polite.paused_until == 220.0
    assert polite.throttled() == 120.0


def test_observe_ignores_other_hosts_and_hosts_that_only_end_in_arxiv():
    clock = FakeClock()
    polite = limiter(clock)

    asyncio.run(polite.observe(response(429, url="https://api.deepseek.com/chat")))
    asyncio.run(polite.observe(response(429, url="https://notarxiv.org/api")))

    assert polite.paused_until == 0.0


def test_watch_responses_adds_the_hook_after_existing_ones():
    polite = PoliteRateLimiter()

    async def existing(_response):
        return None

    client = httpx.AsyncClient(event_hooks={"response": [existing]})
    watch_responses(client, polite)

    assert client.event_hooks["response"] == [existing, polite.observe]
    asyncio.run(client.aclose())


def test_a_cancelled_wait_releases_the_limiter():
    async def main():
        polite = PoliteRateLimiter(min_interval=0.0, jitter=0.0, cooldown=60.0)
        polite.throttled()
        waiting = asyncio.create_task(polite.__aenter__())
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        return polite._lock.locked()

    assert asyncio.run(main()) is False


class StaticExtractor:
    def __init__(self, text):
        self.text = text
        self.downloads = 0

    def cursor_for_offset(self, offset):
        return f"offset-{offset}"

    async def fetch_page(self, query, cursor, page_size):
        return ListingPage(records=(RECORD,), entries=1, next_cursor=None)

    async def fetch_full_text(self, record):
        self.downloads += 1
        return self.text


def test_full_text_is_downloaded_once_and_then_read_from_the_cache(tmp_path):
    inner = StaticExtractor("Dragonfly 44 has an effective radius of 4.6 kpc.")
    messages = []
    cache = FullTextCache(inner, tmp_path / "full_text", messages.append)

    first = asyncio.run(cache.fetch_full_text(RECORD))
    second = asyncio.run(cache.fetch_full_text(RECORD))

    assert first == second == inner.text
    assert inner.downloads == 1
    assert sorted(path.name for path in (tmp_path / "full_text").iterdir()) == ["2401.00001v2.txt"]
    assert messages == [f"Full text from the cache: {len(inner.text):,} characters"]


def test_an_abstract_fallback_or_empty_text_is_not_cached(tmp_path):
    for text in (RECORD.abstract, ""):
        inner = StaticExtractor(text)
        cache = FullTextCache(inner, tmp_path / "full_text", lambda _message: None)

        asyncio.run(cache.fetch_full_text(RECORD))
        asyncio.run(cache.fetch_full_text(RECORD))

        assert inner.downloads == 2
    assert not (tmp_path / "full_text").exists()


def test_cache_file_names_are_safe_for_old_style_ids_and_listing_calls_pass_through(tmp_path):
    cache = FullTextCache(StaticExtractor("text"), tmp_path, lambda _message: None)
    old_style = RawRecord(record_id="astro-ph/0601001v1", title="", abstract="", source_url="")

    assert cache.path_for(old_style) == tmp_path / "astro-ph_0601001v1.txt"
    assert cache.cursor_for_offset(200) == "offset-200"
    assert asyncio.run(cache.fetch_page("q", None, 10)).records == (RECORD,)
