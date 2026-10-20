"""sci-etl-core's extractor contract, run against the catalogue's logging wrapper around the arXiv extractor."""

import httpx
import pytest
from sci_etl_core import AsyncArxivExtractor
from sci_etl_core.parsers.base import Parser
from sci_etl_core.testing import ExtractorContract

from udg_catalogue.progress import LoggingExtractor

LISTED = 5


class StubParser(Parser):
    def extract_text(self, content):
        return content.decode()


async def no_sleep(_delay):
    return None


def arxiv(request):
    if request.url.host == "arxiv.org":
        return httpx.Response(200, content=b"source of " + request.url.path.encode())
    start = int(request.url.params["start"])
    end = min(start + int(request.url.params["max_results"]), LISTED)
    entries = "".join(
        f"<entry><id>http://arxiv.org/abs/2401.0000{index}v1</id>"
        f"<title>Paper {index}</title><summary>Abstract {index}.</summary></entry>"
        for index in range(start, end)
    )
    return httpx.Response(200, content=f'<feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>'.encode())


def unavailable(_request):
    return httpx.Response(503)


def logging_extractor(handler, messages):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    inner = AsyncArxivExtractor(
        client, StubParser(), StubParser(), max_retries=1, sleep_before_search=0.0, sleep=no_sleep
    )
    return LoggingExtractor(inner, messages.append)


class TestLoggingExtractor(ExtractorContract):
    @pytest.fixture
    def messages(self):
        return []

    @pytest.fixture
    def make_extractor(self, messages):
        return lambda: logging_extractor(arxiv, messages)

    @pytest.fixture
    def make_unavailable_extractor(self, messages):
        return lambda: logging_extractor(unavailable, messages)
