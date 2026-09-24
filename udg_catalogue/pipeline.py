from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx
from sci_etl_core import (
    AsyncArxivExtractor,
    AsyncCsvUpsertExporter,
    AsyncEntityExtractor,
    AsyncETLPipeline,
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
from sci_etl_core.config import PipelineConfig
from sci_etl_core.parsers import LatexTarballParser, PdfPlumberParser
from sci_etl_core.search import AsyncTextSearchStore

from udg_catalogue.config import FRACTION_BOUNDS, KEY_COLUMN, MEASUREMENT_FIELDS, CatalogueConfig
from udg_catalogue.literature import PaperLibrary, build_chunker, open_paper_library
from udg_catalogue.naming import GalaxyNameNormalizer
from udg_catalogue.progress import LoggingExtractor, LoggingParser, LoggingRelevanceFilter, PipelineEventLogger
from udg_catalogue.prompts import EXTRACTION_PROMPT, RELEVANCE_PROMPT
from udg_catalogue.validation import ValidatedEntityExtractor, build_galaxy_validator

EXTRACTION_RESULT_KEY = "galaxies"
PipelineBuilder = Callable[..., AsyncETLPipeline]


class NoEntityExtractor(AsyncEntityExtractor):
    async def extract(self, text: str | bytes) -> list[dict[str, Any]]:
        return []


class UnindexedRelevanceFilter(AsyncRelevanceFilter):
    def __init__(self, inner: AsyncRelevanceFilter, text_store: AsyncTextSearchStore) -> None:
        self._inner = inner
        self._text_store = text_store

    async def is_relevant(self, record: RawRecord) -> bool:
        if await self._text_store.get_documents([record.record_id]):
            return False
        return await self._inner.is_relevant(record)


def build_catalogue_exporter() -> AsyncCsvUpsertExporter:
    return AsyncCsvUpsertExporter(
        key_column=KEY_COLUMN,
        value_columns=list(MEASUREMENT_FIELDS),
        normalizer=GalaxyNameNormalizer(),
        numeric_clip=dict(FRACTION_BOUNDS),
    )


def build_http_client(config: CatalogueConfig) -> httpx.AsyncClient:
    return config.http.build_client()


def build_llm_client(config: CatalogueConfig) -> AsyncLLMClient:
    return AsyncOpenAICompatibleClient.from_config(config.llm)


def build_entity_extractor(
    config: CatalogueConfig,
    llm_client: AsyncLLMClient,
    logger: logging.Logger,
) -> ValidatedEntityExtractor:
    return ValidatedEntityExtractor(
        AsyncLLMEntityExtractor(
            llm_client=llm_client,
            system_prompt=EXTRACTION_PROMPT,
            result_key=EXTRACTION_RESULT_KEY,
            timeout=config.llm.timeout,
        ),
        build_galaxy_validator(),
        logger=logger.info,
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
) -> AsyncETLPipeline:
    cache = AsyncSqliteLLMResponseCache(config.paths.llm_cache)
    cached_llm = CachingLLMClient(llm_client, cache, model=config.llm.model, logger=logger.warning)
    relevance_filter: AsyncRelevanceFilter = AsyncLLMRelevanceFilter(
        llm_client=cached_llm, system_prompt=RELEVANCE_PROMPT
    )
    entity_extractor: AsyncEntityExtractor
    if indexing:
        relevance_filter = UnindexedRelevanceFilter(relevance_filter, library.text_store)
        entity_extractor = NoEntityExtractor()
        state_manager = AsyncFileStateManager(config.paths.indexed_ids, config.paths.indexing_metadata)
    else:
        entity_extractor = build_entity_extractor(config, cached_llm, logger)
        state_manager = AsyncFileStateManager(config.paths.processed_ids, config.paths.pipeline_metadata)
    extractor = AsyncArxivExtractor.from_config(
        config.http,
        config.pipeline,
        client=http_client,
        pdf_parser=LoggingParser(PdfPlumberParser(), "PDF", logger.info),
        latex_parser=LoggingParser(LatexTarballParser(), "LaTeX source", logger.info),
        logger=logger.info,
    )
    return AsyncETLPipeline.from_config(
        config.pipeline,
        extractor=LoggingExtractor(extractor, logger.info),
        relevance_filter=LoggingRelevanceFilter(relevance_filter, logger.info),
        entity_extractor=entity_extractor,
        exporter=build_catalogue_exporter(),
        state_manager=state_manager,
        destination=str(config.paths.raw_catalogue),
        logger=logger.warning,
        closeables=[http_client, llm_client, cache, *library.closeables],
        memory_ingestor=library.memory_ingestor(build_chunker(config.embeddings), logger.warning),
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
) -> AsyncETLPipeline:
    return _assemble(config, logger, http_client, llm_client, library, shutdown, indexing=False)


def build_indexing_pipeline(
    config: CatalogueConfig,
    logger: logging.Logger,
    http_client: httpx.AsyncClient,
    llm_client: AsyncLLMClient,
    library: PaperLibrary,
    shutdown: ShutdownSignal | None = None,
) -> AsyncETLPipeline:
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
