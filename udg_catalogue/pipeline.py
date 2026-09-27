from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

import httpx
from sci_etl_core import (
    AsyncArxivExtractor,
    AsyncCsvExporter,
    AsyncEntityExtractor,
    AsyncETLPipeline,
    AsyncExporter,
    AsyncFileStateManager,
    AsyncLLMClient,
    AsyncLLMEntityExtractor,
    AsyncLLMRelevanceFilter,
    AsyncOpenAICompatibleClient,
    AsyncRelevanceFilter,
    AsyncSqliteLLMResponseCache,
    CachingLLMClient,
    RawRecord,
    ShutdownSignal,
)
from sci_etl_core.claims import AsyncRejectionStore, AsyncSqliteRejectionStore
from sci_etl_core.config import PipelineConfig
from sci_etl_core.parsers import LatexTarballParser, PdfPlumberParser
from sci_etl_core.search import AsyncTextSearchStore

from udg_catalogue.config import KEY_COLUMN, MEASUREMENT_FIELDS, CatalogueConfig
from udg_catalogue.literature import PaperLibrary, build_chunker, open_paper_library
from udg_catalogue.progress import LoggingExtractor, LoggingParser, LoggingRelevanceFilter, PipelineEventLogger
from udg_catalogue.prompts import EXTRACTION_PROMPT, RELEVANCE_PROMPT
from udg_catalogue.validation import build_galaxy_validator

EXTRACTION_RESULT_KEY = "galaxies"
PipelineBuilder = Callable[..., AsyncETLPipeline[Any]]


class NoEntityExtractor(AsyncEntityExtractor[dict[str, Any]]):
    async def extract(self, text: str | bytes) -> list[dict[str, Any]]:
        return []


class DiscardingExporter(AsyncExporter[Any]):
    """Keep nothing: the indexing run fills the paper search index and must never touch the catalogue."""

    async def write(self, record: RawRecord, entities: Sequence[Any]) -> None:
        return None


class UnindexedRelevanceFilter(AsyncRelevanceFilter):
    def __init__(self, inner: AsyncRelevanceFilter, text_store: AsyncTextSearchStore) -> None:
        self._inner = inner
        self._text_store = text_store

    async def is_relevant(self, record: RawRecord) -> bool:
        if await self._text_store.get_documents([record.record_id]):
            return False
        return await self._inner.is_relevant(record)


def build_catalogue_exporter(config: CatalogueConfig) -> AsyncCsvExporter:
    """Write the raw catalogue: one row per galaxy a paper reports, tagged with the paper's arXiv id."""
    return AsyncCsvExporter(config.paths.raw_catalogue, [KEY_COLUMN, *MEASUREMENT_FIELDS])


def build_http_client(config: CatalogueConfig) -> httpx.AsyncClient:
    return config.http.build_client()


def build_llm_client(config: CatalogueConfig) -> AsyncLLMClient:
    return AsyncOpenAICompatibleClient.from_config(config.llm)


def build_entity_extractor(
    config: CatalogueConfig,
    llm_client: AsyncLLMClient,
    rejections: AsyncRejectionStore | None = None,
) -> AsyncLLMEntityExtractor[dict[str, Any]]:
    """Extract galaxies and apply the catalogue rules; each rejected galaxy is logged with its reasons and kept."""
    return AsyncLLMEntityExtractor(
        llm_client,
        EXTRACTION_PROMPT,
        result_key=EXTRACTION_RESULT_KEY,
        timeout=config.llm.timeout,
        validator=build_galaxy_validator(),
        rejections=rejections,
        label_field=KEY_COLUMN,
    )


def _assemble(
    config: CatalogueConfig,
    logger: logging.Logger,
    http_client: httpx.AsyncClient,
    llm_client: AsyncLLMClient,
    library: PaperLibrary,
    shutdown: ShutdownSignal | None,
    *,
    indexing: bool,
) -> AsyncETLPipeline[Any]:
    cache = AsyncSqliteLLMResponseCache(config.paths.llm_cache)
    cached_llm = CachingLLMClient(llm_client, cache, model=config.llm.model)
    relevance_filter: AsyncRelevanceFilter = AsyncLLMRelevanceFilter(
        llm_client=cached_llm, system_prompt=RELEVANCE_PROMPT
    )
    entity_extractor: AsyncEntityExtractor[dict[str, Any]]
    exporter: AsyncExporter[Any]
    closeables: list[Any] = [http_client, llm_client, cache, *library.closeables]
    if indexing:
        relevance_filter = UnindexedRelevanceFilter(relevance_filter, library.text_store)
        entity_extractor = NoEntityExtractor()
        exporter = DiscardingExporter()
        state_manager = AsyncFileStateManager(config.paths.indexed_ids, config.paths.indexing_metadata)
    else:
        rejections = AsyncSqliteRejectionStore(config.paths.rejections)
        closeables.append(rejections)
        entity_extractor = build_entity_extractor(config, cached_llm, rejections)
        exporter = build_catalogue_exporter(config)
        state_manager = AsyncFileStateManager(config.paths.processed_ids, config.paths.pipeline_metadata)
    extractor = AsyncArxivExtractor.from_config(
        config.http,
        config.pipeline,
        client=http_client,
        pdf_parser=LoggingParser(PdfPlumberParser(), "PDF", logger.info),
        latex_parser=LoggingParser(LatexTarballParser(), "LaTeX source", logger.info),
        full_text=config.full_text,
    )
    return AsyncETLPipeline.from_config(
        config.pipeline,
        extractor=LoggingExtractor(extractor, logger.info),
        relevance_filter=LoggingRelevanceFilter(relevance_filter, logger.info),
        entity_extractor=entity_extractor,
        exporter=exporter,
        state_manager=state_manager,
        closeables=closeables,
        memory_ingestor=library.memory_ingestor(build_chunker(config.embeddings)),
        shutdown=shutdown,
        on_event=PipelineEventLogger(logger.info, logger.warning),
        usage_sources=[llm_client, *library.usage_sources],
    )


def build_pipeline(
    config: CatalogueConfig,
    logger: logging.Logger,
    http_client: httpx.AsyncClient,
    llm_client: AsyncLLMClient,
    library: PaperLibrary,
    shutdown: ShutdownSignal | None = None,
) -> AsyncETLPipeline[Any]:
    return _assemble(config, logger, http_client, llm_client, library, shutdown, indexing=False)


def build_indexing_pipeline(
    config: CatalogueConfig,
    logger: logging.Logger,
    http_client: httpx.AsyncClient,
    llm_client: AsyncLLMClient,
    library: PaperLibrary,
    shutdown: ShutdownSignal | None = None,
) -> AsyncETLPipeline[Any]:
    return _assemble(config, logger, http_client, llm_client, library, shutdown, indexing=True)


def run_arguments(pipeline: PipelineConfig, start_index: int | None) -> dict[str, Any]:
    arguments = pipeline.run_arguments()
    if start_index is not None:
        arguments.update(start_index=start_index, newest_first=False)
    return arguments


async def _run(
    build: PipelineBuilder,
    config: CatalogueConfig,
    logger: logging.Logger,
    start_index: int | None,
    shutdown: ShutdownSignal | None,
) -> int:
    library = open_paper_library(config)
    http_client = build_http_client(config)
    llm_client = build_llm_client(config)
    async with build(config, logger, http_client, llm_client, library, shutdown) as pipeline:
        return await pipeline.run(**run_arguments(config.pipeline, start_index))


async def run_ingestion(
    config: CatalogueConfig,
    logger: logging.Logger,
    start_index: int | None = None,
    shutdown: ShutdownSignal | None = None,
) -> int:
    return await _run(build_pipeline, config, logger, start_index, shutdown)


async def run_paper_indexing(
    config: CatalogueConfig,
    logger: logging.Logger,
    start_index: int | None = None,
    shutdown: ShutdownSignal | None = None,
) -> int:
    return await _run(build_indexing_pipeline, config, logger, start_index, shutdown)
