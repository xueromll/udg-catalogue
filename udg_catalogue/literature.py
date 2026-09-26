from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable, Collection, Coroutine, Hashable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from sci_etl_core import AsyncCompositeIngestor, MemoryIngestor
from sci_etl_core.config import SearchConfig
from sci_etl_core.discovery import DiscoveryResult, Facet
from sci_etl_core.embeddings import (
    AsyncChunkIngestor,
    AsyncEmbedder,
    AsyncEmbeddingStore,
    AsyncOpenAIEmbedder,
    AsyncSentenceTransformerEmbedder,
    AsyncSimilarArticleFinder,
    AsyncSqliteEmbeddingStore,
    SlidingWindowChunker,
)
from sci_etl_core.search import (
    AsyncEdgeSource,
    AsyncHybridSearcher,
    AsyncSearchIndexer,
    AsyncSqliteFts5Store,
    AsyncTextSearchStore,
    DiscoveryGraph,
    EmbeddingEdgeSource,
    MetadataEdgeSource,
    MetadataFilter,
    Node,
    RangeFilter,
    SearchDocument,
    SearchFilter,
    SearchMode,
    build_discovery_graph,
    describe,
    filter_graph,
    parse_query,
)

from udg_catalogue.config import PAPER_FACET_KEYS, CatalogueConfig, EmbeddingsConfig

DISPLAY_FACET_KEYS: tuple[str, ...] = ("categories", "year")
GRAPH_TAG_KEYS: tuple[str, ...] = ("categories", "authors")
T = TypeVar("T")


def build_embedder(config: EmbeddingsConfig) -> AsyncEmbedder:
    if config.provider == "openai":
        return AsyncOpenAIEmbedder(api_key=config.api_key, base_url=config.base_url, model=config.model)
    return AsyncSentenceTransformerEmbedder(config.model)


def build_chunker(config: EmbeddingsConfig) -> SlidingWindowChunker:
    return SlidingWindowChunker(config.chunk_words, config.overlap_words)


def galaxy_query(galaxy_name: str) -> str:
    words = " ".join(str(galaxy_name).replace('"', " ").split())
    return f'"{words}"'


def paper_filters(
    categories: Collection[str] = (),
    years: tuple[int, int] | None = None,
) -> list[SearchFilter]:
    filters: list[SearchFilter] = []
    if categories:
        filters.append(MetadataFilter("categories", frozenset(categories)))
    if years is not None:
        filters.append(RangeFilter("year", low=years[0], high=years[1]))
    return filters


class CachedEdgeSource(AsyncEdgeSource):
    def __init__(self, source: AsyncEdgeSource) -> None:
        self._source = source
        self._lists: dict[tuple[str, int], list[tuple[str, float]]] = {}

    @property
    def source(self) -> AsyncEdgeSource:
        return self._source

    @property
    def kind(self) -> str:
        return self._source.kind

    async def neighbours(self, record_ids: Sequence[str], limit: int) -> dict[str, list[tuple[str, float]]]:
        wanted = list(dict.fromkeys(record_ids))
        missing = [record_id for record_id in wanted if (record_id, limit) not in self._lists]
        if missing:
            fetched = await self._source.neighbours(missing, limit)
            for record_id in missing:
                self._lists[(record_id, limit)] = list(fetched.get(record_id, []))
        return {record_id: list(self._lists[(record_id, limit)]) for record_id in wanted}

    def clear(self) -> None:
        self._lists.clear()

    def __len__(self) -> int:
        return len(self._lists)


@dataclass(frozen=True, slots=True)
class LibraryOverview:
    papers: int
    years: tuple[int, ...]
    categories: tuple[tuple[str, int], ...]


class PaperLibrary:
    def __init__(
        self,
        text_store: AsyncTextSearchStore,
        search_config: SearchConfig | None = None,
        embedder: AsyncEmbedder | None = None,
        vector_store: AsyncEmbeddingStore | None = None,
        closeables: Sequence[Any] = (),
    ) -> None:
        if (embedder is None) != (vector_store is None):
            raise ValueError("Pass both an embedder and a vector store, or neither")
        self._text_store = text_store
        self._search_config = search_config or SearchConfig()
        self._embedder = embedder
        self._vector_store = vector_store
        self._closeables = list(closeables)
        self._edge_sources: list[CachedEdgeSource] | None = None

    @property
    def text_store(self) -> AsyncTextSearchStore:
        return self._text_store

    @property
    def semantic(self) -> bool:
        return self._embedder is not None

    @property
    def closeables(self) -> list[Any]:
        return list(self._closeables)

    @property
    def usage_sources(self) -> list[AsyncEmbedder]:
        return [] if self._embedder is None else [self._embedder]

    def memory_ingestor(self, chunker: SlidingWindowChunker, logger: Callable[[str], None]) -> MemoryIngestor:
        indexer = AsyncSearchIndexer(store=self._text_store)
        if self._embedder is None or self._vector_store is None:
            return indexer
        chunks = AsyncChunkIngestor(chunker=chunker, embedder=self._embedder, store=self._vector_store)
        return AsyncCompositeIngestor(chunks, indexer, logger=logger)

    def searcher(self, logger: Callable[[str], None] | None = None) -> AsyncHybridSearcher:
        finder = None
        if self._embedder is not None and self._vector_store is not None:
            finder = AsyncSimilarArticleFinder(self._embedder, self._vector_store)
        return AsyncHybridSearcher(
            self._text_store,
            finder,
            params=self._search_config.hybrid.to_params(),
            fusion=self._search_config.fusion.to_params(),
            logger=logger,
        )

    async def count(self) -> int:
        return await self._text_store.count()

    async def overview(self) -> LibraryOverview:
        papers, counts = await asyncio.gather(
            self._text_store.count(),
            self._text_store.facet_counts(DISPLAY_FACET_KEYS),
        )
        years = sorted(int(year) for year, _count in counts["year"] if year.isdecimal())
        return LibraryOverview(papers, tuple(years), counts["categories"])

    async def documents(self, record_ids: Collection[str]) -> dict[str, SearchDocument]:
        return await self._text_store.get_documents(record_ids)

    async def search(
        self,
        query: str,
        *,
        mode: SearchMode = "hybrid",
        filters: Sequence[SearchFilter] = (),
        top_k: int = 20,
        logger: Callable[[str], None] | None = None,
    ) -> DiscoveryResult:
        started = time.perf_counter()
        node = parse_query(query)
        lexical_node = None if mode == "semantic" else node
        outcome, facet_counts, matched_ids = await asyncio.gather(
            self.searcher(logger).search(query, top_k, mode=mode, filters=filters),
            self._text_store.facet_counts(DISPLAY_FACET_KEYS, query=lexical_node, filters=filters),
            self._matched_ids(lexical_node, filters),
        )
        return DiscoveryResult(
            query_text=query,
            chips=tuple(describe(node)),
            hits=tuple(outcome.hits),
            graph=None,
            facets=tuple(Facet(key, facet_counts[key]) for key in DISPLAY_FACET_KEYS),
            total_matched=len(outcome.hits) if matched_ids is None else len(matched_ids),
            elapsed_ms=(time.perf_counter() - started) * 1000,
            degraded=outcome.degraded,
            skipped=outcome.skipped,
        )

    async def _matched_ids(self, node: Node | None, filters: Sequence[SearchFilter]) -> frozenset[str] | None:
        if node is None:
            return None
        return await self._text_store.filter_ids(node, filters)

    def edge_sources(self) -> list[CachedEdgeSource]:
        if self._edge_sources is None:
            sources: list[AsyncEdgeSource] = []
            if self._embedder is not None and self._vector_store is not None:
                sources.append(
                    EmbeddingEdgeSource(
                        self._embedder,
                        self._vector_store,
                        self._text_store,
                        chunk_pool_factor=self._search_config.hybrid.chunk_pool_factor,
                    )
                )
            sources.append(MetadataEdgeSource(self._text_store, keys=GRAPH_TAG_KEYS))
            self._edge_sources = [CachedEdgeSource(source) for source in sources]
        return list(self._edge_sources)

    def forget_neighbours(self) -> None:
        for source in self._edge_sources or ():
            source.clear()

    async def related_papers(self, record_id: str, filters: Sequence[SearchFilter] = ()) -> DiscoveryGraph:
        graph = await build_discovery_graph(
            record_id,
            self.edge_sources(),
            self._text_store,
            params=self._search_config.graph.to_params(),
        )
        return filter_graph(graph, filters=filters) if filters else graph

    async def aclose(self) -> None:
        for resource in self._closeables:
            close = getattr(resource, "aclose", None)
            if close is not None:
                await close()


def open_paper_library(config: CatalogueConfig, embedder: AsyncEmbedder | None = None) -> PaperLibrary:
    text_store = AsyncSqliteFts5Store(
        config.paths.search_index,
        facet_keys=PAPER_FACET_KEYS,
        weights=config.search.bm25.to_weights(),
    )
    closeables: list[Any] = [text_store]
    if not config.embeddings.enabled:
        return PaperLibrary(text_store, config.search, closeables=closeables)
    if embedder is None:
        embedder = build_embedder(config.embeddings)
        closeables.append(embedder)
    vector_store = AsyncSqliteEmbeddingStore(config.paths.vector_memory)
    closeables.append(vector_store)
    return PaperLibrary(text_store, config.search, embedder, vector_store, closeables)


class PaperLibraryService:
    def __init__(self, open_library: Callable[[], PaperLibrary]) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="paper-library", daemon=True)
        self._thread.start()
        self._library = self._submit(self._open(open_library))
        self._version: Hashable = None

    @property
    def library(self) -> PaperLibrary:
        return self._library

    def run(self, operation: Callable[[PaperLibrary], Awaitable[T]], version: Hashable = None) -> T:
        return self._submit(self._run(operation, version))

    def close(self) -> None:
        if self._loop.is_closed():
            return
        try:
            self._submit(self._library.aclose())
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join()
            self._loop.close()

    def _submit(self, coroutine: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()

    async def _run(self, operation: Callable[[PaperLibrary], Awaitable[T]], version: Hashable) -> T:
        if version != self._version:
            self._library.forget_neighbours()
            self._version = version
        return await operation(self._library)

    @staticmethod
    async def _open(open_library: Callable[[], PaperLibrary]) -> PaperLibrary:
        return open_library()
