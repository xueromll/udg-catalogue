from __future__ import annotations

import logging

import httpx
from sci_etl_core import (
    AsyncArxivExtractor,
    AsyncCsvUpsertExporter,
    AsyncETLPipeline,
    AsyncFileStateManager,
    AsyncLLMClient,
    AsyncLLMEntityExtractor,
    AsyncLLMRelevanceFilter,
    AsyncOpenAICompatibleClient,
)
from sci_etl_core.http_async import build_async_client
from sci_etl_core.parsers import LatexTarballParser, PdfPlumberParser

from udg_catalogue.config import FRACTION_BOUNDS, KEY_COLUMN, MEASUREMENT_FIELDS, CatalogueConfig
from udg_catalogue.naming import GalaxyNameNormalizer
from udg_catalogue.progress import LoggingExtractor, LoggingParser, LoggingRelevanceFilter, PipelineEventLogger
from udg_catalogue.prompts import EXTRACTION_PROMPT, RELEVANCE_PROMPT
from udg_catalogue.validation import ValidatedEntityExtractor, build_galaxy_validator

EXTRACTION_RESULT_KEY = "galaxies"


def build_catalogue_exporter() -> AsyncCsvUpsertExporter:
    return AsyncCsvUpsertExporter(
        key_column=KEY_COLUMN,
        value_columns=list(MEASUREMENT_FIELDS),
        normalizer=GalaxyNameNormalizer(),
        numeric_clip=dict(FRACTION_BOUNDS),
    )


def build_pipeline(
    config: CatalogueConfig,
    logger: logging.Logger,
    http_client: httpx.AsyncClient,
    llm_client: AsyncLLMClient,
) -> AsyncETLPipeline:
    extractor = AsyncArxivExtractor(
        client=http_client,
        pdf_parser=LoggingParser(PdfPlumberParser(), "PDF", logger.info),
        latex_parser=LoggingParser(LatexTarballParser(), "LaTeX source", logger.info),
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
        extractor=LoggingExtractor(extractor, logger.info),
        relevance_filter=LoggingRelevanceFilter(
            AsyncLLMRelevanceFilter(llm_client=llm_client, system_prompt=RELEVANCE_PROMPT),
            logger.info,
        ),
        entity_extractor=entity_extractor,
        exporter=build_catalogue_exporter(),
        state_manager=AsyncFileStateManager(config.paths.processed_ids, config.paths.pipeline_metadata),
        destination=str(config.paths.raw_catalogue),
        max_concurrency=config.pipeline.max_workers,
        logger=logger.warning,
        closeables=[http_client, llm_client],
        on_event=PipelineEventLogger(logger.info, logger.warning),
        usage_sources=[llm_client],
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
