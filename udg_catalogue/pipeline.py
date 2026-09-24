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
from sci_etl_core.observability import PageFinished, PipelineEvent, RunFinished, RunMetrics
from sci_etl_core.parsers import LatexTarballParser, PdfPlumberParser
from sci_etl_core.search import AsyncTextSearchStore

from udg_catalogue.config import FRACTION_BOUNDS, KEY_COLUMN, MEASUREMENT_FIELDS, CatalogueConfig
from udg_catalogue.literature import PaperLibrary, build_chunker, open_paper_library
from udg_catalogue.naming import GalaxyNameNormalizer
from udg_catalogue.progress import LoggingExtractor, LoggingParser, LoggingRelevanceFilter, PipelineEventLogger
from udg_catalogue.prompts import EXTRACTION_PROMPT, RELEVANCE_PROMPT
from udg_catalogue.validation import build_galaxy_validator

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


def describe_run(metrics: RunMetrics) -> str:
    summary = (
        f"Run {metrics.outcome} in {metrics.duration_seconds:.0f}s: {metrics.pages} pages, "
        f"{metrics.processed} relevant, {metrics.irrelevant} irrelevant, {metrics.failed} failed, "
        f"{metrics.entities_exported} galaxies exported, {metrics.memory_faults} memory faults"
    )
    if metrics.token_usage is None:
        return summary
    usage = metrics.token_usage
    return f"{summary}, {usage.total_tokens} tokens in {usage.requests} requests"


def progress_logger(log: Callable[[str], None]) -> Callable[[PipelineEvent], None]:
    def on_event(event: PipelineEvent) -> None:
        if isinstance(event, PageFinished):
            metrics = event.metrics
            log(
                f"Page at offset {event.offset} finished in {event.duration_seconds:.1f}s; so far "
                f"{metrics.processed} relevant, {metrics.irrelevant} irrelevant, {metrics.failed} failed"
            )
        elif isinstance(event, RunFinished):
            log(describe_run(event.metrics))

    return on_event


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
) -> AsyncLLMEntityExtractor:
    return AsyncLLMEntityExtractor(
        llm_client=llm_client,
        system_prompt=EXTRACTION_PROMPT,
        result_key=EXTRACTION_RESULT_KEY,
        timeout=config.llm.timeout,
        validator=build_galaxy_validator(),
        logger=logger.info,
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
        pdf_parser=PdfPlumberParser(),
        latex_parser=LatexTarballParser(),
        max_retries=config.http.max_retries,
        backoff_factor=config.http.backoff_factor,
        sleep_before_search=config.pipeline.search_delay,
        logger=logger.info,
    )
    entity_extractor = ValidatedEntityExtractor(
        AsyncLLMEntityExtractor(
            llm_client=llm_client,
            system_prompt=EXTRACTION_PROMPT,
            result_key=EXTRACTION_RESULT_KEY,
            timeout=config.llm.timeout,
        ),
        build_galaxy_validator(),
        logger=logger.info,
    )
    return AsyncETLPipeline(
        extractor=extractor,
        relevance_filter=AsyncLLMRelevanceFilter(llm_client=llm_client, system_prompt=RELEVANCE_PROMPT),
        entity_extractor=entity_extractor,
        exporter=build_catalogue_exporter(),
        state_manager=state_manager,
        destination=str(config.paths.raw_catalogue),
        logger=logger.warning,
        closeables=[http_client, llm_client],
    )


async def run_ingestion(config: CatalogueConfig, logger: logging.Logger, start_index: int | None = 0) -> int:
    http_client = build_async_client(timeout=config.http.timeout, user_agent=config.http.user_agent)
    llm_client = AsyncOpenAICompatibleClient(
        api_key=config.llm.api_key,
        base_url=config.llm.base_url,
        model=config.llm.model,
        default_timeout=config.llm.timeout,
    )
    async with build_pipeline(config, logger, http_client, llm_client) as pipeline:
        return await pipeline.run(
            query=config.pipeline.search_query,
            page_size=config.pipeline.page_size,
            total_limit=config.pipeline.max_records,
            sleep_between=config.pipeline.sleep_between,
            start_index=start_index,
        )
