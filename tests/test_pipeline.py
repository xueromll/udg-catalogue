import asyncio
import gzip
import json
import logging

import httpx
import pandas as pd
import pytest
from fakes import HashingEmbedder
from pydantic import SecretStr
from sci_etl_core import (
    AsyncArxivExtractor,
    AsyncCascadingRelevanceFilter,
    AsyncLLMClient,
    AsyncLLMRelevanceFilter,
    PipelineInterrupted,
    ShutdownSignal,
)
from sci_etl_core.claims import AsyncSqliteRejectionStore
from sci_etl_core.config import PipelineConfig
from sci_etl_core.embeddings import AsyncSqliteEmbeddingStore, InMemoryEmbeddingStore
from sci_etl_core.search import AsyncSqliteFts5Store, InMemoryTextSearchStore

from udg_catalogue import literature as literature_module
from udg_catalogue import pipeline as pipeline_module
from udg_catalogue.arxiv import PoliteRateLimiter
from udg_catalogue.config import PAPER_FACET_KEYS, PrescreenConfig
from udg_catalogue.literature import PaperLibrary
from udg_catalogue.pipeline import (
    EXTRACTION_RESULT_KEY,
    build_relevance_filter,
    forget_papers,
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
        "dark_matter_fraction": 0.99,
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


async def unresolved_rejections(config):
    store = AsyncSqliteRejectionStore(config.paths.rejections)
    try:
        return await store.unresolved()
    finally:
        await store.aclose()


def extraction_calls(llm):
    return [content for prompt, content in llm.calls if prompt == EXTRACTION_PROMPT]


def relevance_calls(llm):
    return [content for prompt, content in llm.calls if prompt == RELEVANCE_PROMPT]


def with_prescreen(config, **settings):
    return config.model_copy(update={"prescreen": PrescreenConfig(enabled=True, **settings)})


def state_ids(path):
    return set(path.read_text(encoding="utf-8").split()) if path.is_file() else set()


def test_ingestion_exports_galaxies_and_remembers_each_relevant_paper(ingestion_config, monkeypatch, caplog):
    arxiv = FakeArxiv()
    llm = ScriptedLLMClient()
    embedder = HashingEmbedder()
    created = install_fakes(monkeypatch, arxiv, llm, embedder)
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    caplog.set_level(logging.INFO, logger="sci_etl_core")

    processed = asyncio.run(run_ingestion(ingestion_config, logging.getLogger(LOGGER_NAME)))

    assert processed == 1
    raw = pd.read_csv(ingestion_config.paths.raw_catalogue, dtype={"record_id": str})
    assert raw.columns.tolist() == ["record_id", *EXTRACTED_GALAXIES[0], "extra"]
    assert raw["extra"].isna().all()
    assert raw.drop(columns="extra").to_dict("records") == [{"record_id": OBSERVATIONAL_ID, **EXTRACTED_GALAXIES[0]}]
    assert "Entity rejected by validation: 'mock_udg_1' (name matches simulation keyword 'mock')" in caplog.messages
    (rejected,) = asyncio.run(unresolved_rejections(ingestion_config))
    assert (rejected.record_id, rejected.entity) == (OBSERVATIONAL_ID, EXTRACTED_GALAXIES[1])
    assert [violation.code for violation in rejected.violations] == ["simulation-keyword"]
    assert rejected.stamp.model == ingestion_config.llm.model
    assert set(ingestion_config.paths.processed_ids.read_text(encoding="utf-8").split()) == {
        OBSERVATIONAL_ID,
        SIMULATED_ID,
    }
    metadata = json.loads(ingestion_config.paths.pipeline_metadata.read_text(encoding="utf-8"))
    assert metadata["cursor"] == "2"
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


def test_arxiv_requests_share_one_polite_limiter_that_sees_every_response(ingestion_config, monkeypatch):
    limiters = []
    build_extractor = AsyncArxivExtractor.from_config.__func__

    def recording(cls, *args, **kwargs):
        limiters.append(kwargs["rate_limiter"])
        assert "full_text" not in kwargs
        return build_extractor(cls, *args, **kwargs)

    monkeypatch.setattr(AsyncArxivExtractor, "from_config", classmethod(recording))
    created = install_fakes(monkeypatch, FakeArxiv(), ScriptedLLMClient())

    asyncio.run(run_ingestion(ingestion_config, logging.getLogger(LOGGER_NAME)))

    [limiter] = limiters
    assert isinstance(limiter, PoliteRateLimiter)
    assert limiter.observe in created["http_client"].event_hooks["response"]


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


def test_prescreen_rejects_papers_unlike_the_concepts_without_asking_the_llm(ingestion_config, monkeypatch, caplog):
    arxiv = FakeArxiv()
    llm = ScriptedLLMClient()
    install_fakes(monkeypatch, arxiv, llm)
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    config = with_prescreen(ingestion_config, threshold=0.5, concepts=["imaging of an ultra-diffuse galaxy"])

    processed = asyncio.run(run_ingestion(config, logging.getLogger(LOGGER_NAME)))

    assert processed == 1
    assert len(relevance_calls(llm)) == 1
    assert "Dragonfly 44 revisited" in relevance_calls(llm)[0]
    assert len(extraction_calls(llm)) == 1
    assert state_ids(config.paths.processed_ids) == {OBSERVATIONAL_ID, SIMULATED_ID}
    assert caplog.messages == [
        "Embedding prescreen on: a paper whose title and abstract score below 0.50 against all 1 concepts "
        "is judged not relevant without an LLM call"
    ]


def test_relevance_filter_is_the_llm_alone_unless_the_prescreen_is_on(catalogue_config):
    llm = ScriptedLLMClient()
    library = PaperLibrary(InMemoryTextSearchStore(facet_keys=PAPER_FACET_KEYS))
    logger = logging.getLogger(LOGGER_NAME)

    assert isinstance(build_relevance_filter(catalogue_config, llm, library, logger), AsyncLLMRelevanceFilter)
    semantic = PaperLibrary(
        InMemoryTextSearchStore(facet_keys=PAPER_FACET_KEYS),
        embedder=HashingEmbedder(),
        vector_store=InMemoryEmbeddingStore(),
    )
    cascade = build_relevance_filter(with_prescreen(catalogue_config), llm, semantic, logger)
    assert isinstance(cascade, AsyncCascadingRelevanceFilter)
    with pytest.raises(ValueError, match="needs the paper library's embedder"):
        build_relevance_filter(with_prescreen(catalogue_config), llm, library, logger)


def test_forget_papers_clears_processed_marks_and_names_ids_it_never_saw(ingestion_config, caplog):
    paths = ingestion_config.paths
    paths.processed_ids.write_text("2601.00001v1\n2601.00002v1\n2601.00003v1\n", encoding="utf-8")
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)

    forgotten = asyncio.run(
        forget_papers(
            ingestion_config,
            logging.getLogger(LOGGER_NAME),
            ["2601.00002v1", " 2601.00001v1 ", "2699.99999v9", "2601.00002v1", ""],
        )
    )

    assert forgotten == ["2601.00002v1", "2601.00001v1"]
    assert state_ids(paths.processed_ids) == {"2601.00003v1"}
    assert caplog.messages == [
        "Never processed, so nothing to forget: 2699.99999v9",
        f"Forgot 2 of 3 processed papers in {paths.processed_ids}: 2601.00002v1, 2601.00001v1; "
        "the next run processes them again",
    ]


def test_forget_papers_targets_the_indexing_state_when_indexing(ingestion_config, caplog):
    paths = ingestion_config.paths
    paths.indexed_ids.write_text("2601.00001v1\n", encoding="utf-8")
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)

    forgotten = asyncio.run(
        forget_papers(ingestion_config, logging.getLogger(LOGGER_NAME), ["2601.00005v1"], indexing=True)
    )

    assert forgotten == []
    assert state_ids(paths.indexed_ids) == {"2601.00001v1"}
    assert not paths.processed_ids.exists()
    assert caplog.messages == [
        "Never processed, so nothing to forget: 2601.00005v1",
        f"Forgot 0 of 1 processed papers in {paths.indexed_ids}: none; the next run processes them again",
    ]


def test_a_forgotten_paper_is_extracted_again_from_cached_answers_and_cached_full_text(ingestion_config, monkeypatch):
    arxiv = FakeArxiv()
    llm = ScriptedLLMClient()
    install_fakes(monkeypatch, arxiv, llm)
    config = without_embeddings(ingestion_config)
    logger = logging.getLogger(LOGGER_NAME)
    asyncio.run(run_ingestion(config, logger))
    calls_after_first_run = len(llm.calls)

    asyncio.run(forget_papers(config, logger, [OBSERVATIONAL_ID]))
    processed = asyncio.run(run_ingestion(config, logger, start_index=0))

    assert processed == 1
    assert arxiv.eprint_requests == 1
    assert (config.paths.full_text_cache / f"{OBSERVATIONAL_ID}.txt").is_file()
    assert len(llm.calls) == calls_after_first_run
    raw = pd.read_csv(config.paths.raw_catalogue, dtype={"record_id": str})
    assert raw["record_id"].tolist() == [OBSERVATIONAL_ID]
    assert state_ids(config.paths.processed_ids) == {OBSERVATIONAL_ID, SIMULATED_ID}


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
