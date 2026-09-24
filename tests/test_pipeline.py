import asyncio
import gzip
import json
import logging

import httpx
import pandas as pd
import pytest
from fakes import HashingEmbedder
from pydantic import SecretStr
from sci_etl_core import AsyncLLMClient, PipelineInterrupted, ShutdownSignal, TokenUsage
from sci_etl_core.config import PipelineConfig
from sci_etl_core.embeddings import AsyncSqliteEmbeddingStore
from sci_etl_core.observability import PageFetched, PageFinished, RunFinished, RunMetrics
from sci_etl_core.search import AsyncSqliteFts5Store

from udg_catalogue import literature as literature_module
from udg_catalogue import pipeline as pipeline_module
from udg_catalogue.config import PAPER_FACET_KEYS
from udg_catalogue.pipeline import (
    EXTRACTION_RESULT_KEY,
    describe_run,
    progress_logger,
    run_arguments,
    run_ingestion,
    run_paper_indexing,
)
from udg_catalogue.prompts import EXTRACTION_PROMPT, RELEVANCE_PROMPT

OBSERVATIONAL_ID = "2601.00001v1"
SIMULATED_ID = "2601.00002v1"
LISTING = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2601.00001v1</id>
    <published>2026-01-05T18:00:00Z</published>
    <title>Dragonfly 44 revisited</title>
    <summary>Deep imaging of an ultra-diffuse galaxy.</summary>
    <author><name>Pieter van Dokkum</name></author>
    <category term="astro-ph.GA" scheme="http://arxiv.org/schemas/atom"/>
    <link href="http://arxiv.org/abs/2601.00001v1" rel="alternate" type="text/html"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2601.00002v1</id>
    <published>2026-01-04T18:00:00Z</published>
    <title>Ultra-diffuse galaxies in TNG50</title>
    <summary>Purely simulated galaxies.</summary>
    <author><name>Jane Modeller</name></author>
    <category term="astro-ph.GA" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>"""
EMPTY_LISTING = b'<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
LATEX_SOURCE = rb"\documentclass{article}\begin{document}Dragonfly 44 has an effective radius of 4.6 kpc.\end{document}"
EXTRACTED_GALAXIES = [
    {
        "galaxy_name": "Dragonfly 44",
        "ra": 195.24,
        "dec": 26.98,
        "distance_mpc": 100.0,
        "effective_radius_kpc": 4.6,
        "stellar_mass_solar": 3e8,
        "dark_matter_fraction": 99.0,
    },
    {"galaxy_name": "mock_udg_1", "ra": 10.0, "dec": 10.0},
]
LOGGER_NAME = "udg-test"


class ScriptedLLMClient(AsyncLLMClient):
    def __init__(self):
        self.calls = []
        self.closed = False

    async def complete_json(self, system_prompt, user_content, timeout=None):
        self.calls.append((system_prompt, user_content))
        if system_prompt == RELEVANCE_PROMPT:
            return {"relevant": "TNG50" not in user_content}
        return {EXTRACTION_RESULT_KEY: EXTRACTED_GALAXIES}

    async def aclose(self):
        self.closed = True


class FakeArxiv:
    def __init__(self):
        self.listing_requests = []
        self.eprint_requests = 0

    def handle(self, request):
        if request.url.path == "/api/query":
            self.listing_requests.append(dict(request.url.params))
            start = int(request.url.params["start"])
            return httpx.Response(200, content=LISTING if start == 0 else EMPTY_LISTING)
        if request.url.path.startswith("/e-print/"):
            self.eprint_requests += 1
            return httpx.Response(200, content=gzip.compress(LATEX_SOURCE))
        return httpx.Response(404)


def install_fakes(monkeypatch, arxiv, llm, embedder=None):
    created = {}

    def build_http_client(config):
        created["http_config"] = config.http
        created["http_client"] = httpx.AsyncClient(transport=httpx.MockTransport(arxiv.handle))
        return created["http_client"]

    def build_llm_client(config):
        created["llm_config"] = config.llm
        return llm

    monkeypatch.setattr(pipeline_module, "build_http_client", build_http_client)
    monkeypatch.setattr(pipeline_module, "build_llm_client", build_llm_client)
    monkeypatch.setattr(literature_module, "build_embedder", lambda _config: embedder or HashingEmbedder())
    return created


def without_embeddings(config):
    return config.model_copy(update={"embeddings": config.embeddings.model_copy(update={"enabled": False})})


def indexed_documents(config, record_ids):
    async def read():
        store = AsyncSqliteFts5Store(config.paths.search_index, facet_keys=PAPER_FACET_KEYS)
        try:
            return await store.get_documents(record_ids)
        finally:
            await store.aclose()

    return asyncio.run(read())


def stored_chunks(config):
    async def count():
        store = AsyncSqliteEmbeddingStore(config.paths.vector_memory)
        try:
            return await store.count()
        finally:
            await store.aclose()

    return asyncio.run(count())


def extraction_calls(llm):
    return [content for prompt, content in llm.calls if prompt == EXTRACTION_PROMPT]


def test_ingestion_exports_galaxies_and_remembers_each_relevant_paper(ingestion_config, monkeypatch, caplog):
    arxiv = FakeArxiv()
    llm = ScriptedLLMClient()
    embedder = HashingEmbedder()
    created = install_fakes(monkeypatch, arxiv, llm, embedder)
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)

    processed = asyncio.run(run_ingestion(ingestion_config, logging.getLogger(LOGGER_NAME)))

    assert processed == 1
    assert pd.read_csv(ingestion_config.paths.raw_catalogue).to_dict("records") == [
        {
            "galaxy_name": "Dragonfly 44",
            "ra": 195.24,
            "dec": 26.98,
            "distance_mpc": 100.0,
            "effective_radius_kpc": 4.6,
            "stellar_mass_solar": 3e8,
            "dark_matter_fraction": 1.0,
        }
    ]
    assert "Entity rejected by validation: 'mock_udg_1'" in caplog.messages
    assert set(ingestion_config.paths.processed_ids.read_text(encoding="utf-8").split()) == {
        OBSERVATIONAL_ID,
        SIMULATED_ID,
    }
    metadata = json.loads(ingestion_config.paths.pipeline_metadata.read_text(encoding="utf-8"))
    assert metadata["last_start_index"] == 2
    assert [request["start"] for request in arxiv.listing_requests] == ["0", "2"]
    assert arxiv.listing_requests[0]["search_query"] == ingestion_config.pipeline.search_query
    assert arxiv.listing_requests[0]["max_results"] == "2"
    assert extraction_calls(llm) == [LATEX_SOURCE.decode()]

    documents = indexed_documents(ingestion_config, [OBSERVATIONAL_ID, SIMULATED_ID])
    assert list(documents) == [OBSERVATIONAL_ID]
    paper = documents[OBSERVATIONAL_ID]
    assert paper.title == "Dragonfly 44 revisited"
    assert "effective radius of 4.6 kpc" in paper.body
    assert paper.metadata["categories"] == ["astro-ph.GA"]
    assert paper.metadata["authors"] == ["Pieter van Dokkum"]
    assert paper.metadata["year"] == "2026"
    assert stored_chunks(ingestion_config) == 1
    assert ingestion_config.paths.llm_cache.is_file()

    assert created["http_config"] == ingestion_config.http
    assert created["llm_config"] == ingestion_config.llm
    assert llm.closed
    assert embedder.closed
    assert created["http_client"].is_closed
    assert any(message.startswith("Run completed in") for message in caplog.messages)


def test_clients_are_built_from_the_config_sections(catalogue_config):
    llm = catalogue_config.llm.model_copy(update={"api_key": SecretStr("sk-test")})
    config = catalogue_config.model_copy(update={"llm": llm})

    http_client = pipeline_module.build_http_client(config)
    llm_client = pipeline_module.build_llm_client(config)

    assert http_client.headers["User-Agent"] == config.http.user_agent
    assert llm_client.model == config.llm.model
    asyncio.run(http_client.aclose())
    asyncio.run(llm_client.aclose())


def test_saved_offset_is_used_when_newest_first_is_off(ingestion_config, monkeypatch):
    arxiv = FakeArxiv()
    install_fakes(monkeypatch, arxiv, ScriptedLLMClient())
    pipeline = ingestion_config.pipeline.model_copy(update={"newest_first": False})
    config = ingestion_config.model_copy(update={"pipeline": pipeline})
    config.paths.pipeline_metadata.write_text(
        json.dumps({"last_run_date": None, "last_start_index": 2}),
        encoding="utf-8",
    )

    processed = asyncio.run(run_ingestion(config, logging.getLogger(LOGGER_NAME)))

    assert processed == 0
    assert [request["start"] for request in arxiv.listing_requests] == ["2"]


def test_rescan_starts_at_offset_zero_without_newest_first():
    pipeline = PipelineConfig(search_query="udg", newest_first=True)

    assert run_arguments(pipeline, None) == pipeline.run_arguments()
    assert run_arguments(pipeline, 0) == {**pipeline.run_arguments(), "start_index": 0, "newest_first": False}


def test_paper_indexing_fills_the_index_without_extracting_galaxies(ingestion_config, monkeypatch):
    arxiv = FakeArxiv()
    llm = ScriptedLLMClient()
    install_fakes(monkeypatch, arxiv, llm)
    config = without_embeddings(ingestion_config)

    processed = asyncio.run(run_paper_indexing(config, logging.getLogger(LOGGER_NAME)))

    assert processed == 1
    assert list(indexed_documents(config, [OBSERVATIONAL_ID, SIMULATED_ID])) == [OBSERVATIONAL_ID]
    assert extraction_calls(llm) == []
    assert not config.paths.raw_catalogue.exists()
    assert not config.paths.processed_ids.exists()
    assert not config.paths.vector_memory.exists()
    assert set(config.paths.indexed_ids.read_text(encoding="utf-8").split()) == {OBSERVATIONAL_ID, SIMULATED_ID}


def test_paper_indexing_skips_indexed_papers_and_reuses_cached_answers(ingestion_config, monkeypatch):
    arxiv = FakeArxiv()
    llm = ScriptedLLMClient()
    install_fakes(monkeypatch, arxiv, llm)
    logger = logging.getLogger(LOGGER_NAME)
    asyncio.run(run_ingestion(ingestion_config, logger))
    calls_after_ingestion = len(llm.calls)
    downloads_after_ingestion = arxiv.eprint_requests

    processed = asyncio.run(run_paper_indexing(ingestion_config, logger))

    assert processed == 0
    assert len(llm.calls) == calls_after_ingestion
    assert arxiv.eprint_requests == downloads_after_ingestion
    assert set(ingestion_config.paths.indexed_ids.read_text(encoding="utf-8").split()) == {
        OBSERVATIONAL_ID,
        SIMULATED_ID,
    }


def test_shutdown_request_stops_the_run_before_any_paper(ingestion_config, monkeypatch):
    arxiv = FakeArxiv()
    llm = ScriptedLLMClient()
    install_fakes(monkeypatch, arxiv, llm)
    shutdown = ShutdownSignal()
    shutdown.request()

    with pytest.raises(PipelineInterrupted):
        asyncio.run(run_ingestion(without_embeddings(ingestion_config), logging.getLogger(LOGGER_NAME), None, shutdown))

    assert llm.calls == []
    assert llm.closed


def test_run_summary_reports_outcome_counts_and_tokens():
    metrics = RunMetrics(
        pages=2,
        processed=3,
        irrelevant=4,
        failed=1,
        entities_exported=7,
        memory_faults=0,
        duration_seconds=12.4,
        outcome="completed",
    )

    assert describe_run(metrics) == (
        "Run completed in 12s: 2 pages, 3 relevant, 4 irrelevant, 1 failed, "
        "7 galaxies exported, 0 memory faults"
    )
    metrics.token_usage = TokenUsage(requests=5, prompt_tokens=900, completion_tokens=100)
    assert describe_run(metrics).endswith(", 1000 tokens in 5 requests")


def test_progress_logger_reports_pages_and_the_finished_run():
    messages = []
    on_event = progress_logger(messages.append)
    metrics = RunMetrics(processed=1, irrelevant=2, outcome="completed")

    on_event(PageFetched(offset=0, entries=3, new_records=3))
    on_event(PageFinished(offset=0, duration_seconds=1.25, metrics=metrics))
    on_event(RunFinished(metrics=metrics))

    assert messages == [
        "Page at offset 0 finished in 1.2s; so far 1 relevant, 2 irrelevant, 0 failed",
        describe_run(metrics),
    ]
