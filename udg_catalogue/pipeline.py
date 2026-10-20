from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

import httpx
from sci_etl_core import (
    AsyncArxivExtractor,
    AsyncCascadingRelevanceFilter,
    AsyncCsvExporter,
    AsyncEmbeddingRelevanceFilter,
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


def build_relevance_filter(
    config: CatalogueConfig,
    llm_client: AsyncLLMClient,
    library: PaperLibrary,
    logger: logging.Logger,
) -> AsyncRelevanceFilter:
    """Judge relevance with the LLM, after the embedding prescreen when ``prescreen.enabled`` is set.

    The prescreen embeds a listing's title and abstract with the paper
    library's embedder and rejects it, without an LLM call, when its cosine
    similarity to every ``prescreen.concepts`` entry is below
    ``prescreen.threshold``. A failed embedding lets the paper through to the
    LLM. An active prescreen is logged as a warning, since it changes what the
    run screens and what it costs.

    Raises:
        ValueError: The prescreen is enabled but ``library`` has no embedder.
    """
    judge: AsyncRelevanceFilter = AsyncLLMRelevanceFilter(llm_client=llm_client, system_prompt=RELEVANCE_PROMPT)
    prescreen = config.prescreen
    if not prescreen.enabled:
        return judge
    if library.embedder is None:
        raise ValueError("prescreen.enabled needs the paper library's embedder; set embeddings.enabled")
    logger.warning(
        f"Embedding prescreen on: a paper whose title and abstract score below {prescreen.threshold:.2f} "
        f"against all {len(prescreen.concepts)} concepts is judged not relevant without an LLM call"
    )
    return AsyncCascadingRelevanceFilter(
        AsyncEmbeddingRelevanceFilter(library.embedder, prescreen.concepts, threshold=prescreen.threshold),
        judge,
    )


def build_state_manager(config: CatalogueConfig, *, indexing: bool = False) -> AsyncFileStateManager:
    """The processed-paper files of the ingestion run, or of the paper-indexing run with ``indexing``."""
    paths = config.paths
    if indexing:
        return AsyncFileStateManager(paths.indexed_ids, paths.indexing_metadata)
    return AsyncFileStateManager(paths.processed_ids, paths.pipeline_metadata)


async def forget_papers(
    config: CatalogueConfig,
    logger: logging.Logger,
    record_ids: Sequence[str],
    *,
    indexing: bool = False,
) -> list[str]:
    """Clear the processed mark of each paper in ``record_ids`` and return the ids that had one.

    Call it between runs, and give the run that follows ``start_index=0``, so
    the listing is paged from its first entry and reaches the forgotten papers
    again, as the ``Forgetting`` protocol asks. Ids that were never processed
    are reported as a warning and left as they are, apart from any failed
    attempts they carry, which are cleared too.

    Raises:
        OSError: A state file cannot be read or written.
        StateStoreError: The metadata file was written by a newer sci-etl-core.
    """
    wanted = list(dict.fromkeys(record_id.strip() for record_id in record_ids if record_id.strip()))
    state_manager = build_state_manager(config, indexing=indexing)
    processed = await state_manager.load_processed_ids()
    forgotten = [record_id for record_id in wanted if record_id in processed]
    unknown = [record_id for record_id in wanted if record_id not in processed]
    await state_manager.forget(wanted)
    if unknown:
        logger.warning(f"Never processed, so nothing to forget: {', '.join(unknown)}")
    state_file = config.paths.indexed_ids if indexing else config.paths.processed_ids
    logger.info(
        f"Forgot {len(forgotten)} of {len(processed)} processed papers in {state_file}: "
        f"{', '.join(forgotten) or 'none'}; the next run processes them again"
    )
    return forgotten


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
    relevance_filter = build_relevance_filter(config, cached_llm, library, logger)
    entity_extractor: AsyncEntityExtractor[dict[str, Any]]
    exporter: AsyncExporter[Any]
    closeables: list[Any] = [http_client, llm_client, cache, *library.closeables]
    if indexing:
        relevance_filter = UnindexedRelevanceFilter(relevance_filter, library.text_store)
        entity_extractor = NoEntityExtractor()
        exporter = DiscardingExporter()
    else:
        rejections = AsyncSqliteRejectionStore(config.paths.rejections)
        closeables.append(rejections)
        entity_extractor = build_entity_extractor(config, cached_llm, rejections)
        exporter = build_catalogue_exporter(config)
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
        state_manager=build_state_manager(config, indexing=indexing),
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
