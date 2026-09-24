import asyncio

import pytest
from fakes import HashingEmbedder
from sci_etl_core import AsyncCompositeIngestor, RawRecord, SearchQueryError
from sci_etl_core.embeddings import AsyncOpenAIEmbedder, InMemoryEmbeddingStore
from sci_etl_core.search import (
    AsyncSearchIndexer,
    AsyncSqliteFts5Store,
    EmbeddingEdgeSource,
    InMemoryTextSearchStore,
    MetadataEdgeSource,
    MetadataFilter,
    RangeFilter,
)

from udg_catalogue import literature as literature_module
from udg_catalogue.config import PAPER_FACET_KEYS, EmbeddingsConfig
from udg_catalogue.literature import (
    LibraryOverview,
    PaperLibrary,
    build_chunker,
    build_embedder,
    galaxy_query,
    open_paper_library,
    paper_filters,
    with_paper_library,
)

SHARED_AUTHORS = ["Pieter van Dokkum", "Shany Danieli", "Roberto Abraham"]
PAPERS = [
    (
        RawRecord(
            "2601.00001",
            "Dragonfly 44 is dark matter dominated",
            "Stellar kinematics of the ultra-diffuse galaxy Dragonfly 44.",
            metadata={"categories": ["astro-ph.GA"], "authors": SHARED_AUTHORS, "year": "2016"},
        ),
        "We measure the velocity dispersion of Dragonfly 44 in the Coma cluster.",
    ),
    (
        RawRecord(
            "2601.00002",
            "A galaxy lacking dark matter",
            "NGC 1052-DF2 has globular clusters but little dark matter.",
            metadata={"categories": ["astro-ph.GA"], "authors": SHARED_AUTHORS, "year": "2018"},
        ),
        "The ultra-diffuse galaxy NGC 1052-DF2 has a low velocity dispersion.",
    ),
    (
        RawRecord(
            "2601.00003",
            "Tidal features of dwarf galaxies",
            "Deep photometry of dwarf galaxies in the Fornax cluster.",
            metadata={"categories": ["astro-ph.CO", "astro-ph.GA"], "authors": ["Carla Other"], "year": "2024"},
        ),
        "Tidal tails and shells around dwarf galaxies.",
    ),
]


class RecordingStore:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


def build_library(semantic=True, **options):
    text_store = InMemoryTextSearchStore(facet_keys=PAPER_FACET_KEYS)
    if not semantic:
        return PaperLibrary(text_store, **options)
    return PaperLibrary(text_store, embedder=HashingEmbedder(), vector_store=InMemoryEmbeddingStore(), **options)


async def ingest_papers(library):
    ingestor = library.memory_ingestor(build_chunker(EmbeddingsConfig(chunk_words=8, overlap_words=2)), print)
    for record, text in PAPERS:
        await ingestor.ingest(record, text)


def filled(library):
    asyncio.run(ingest_papers(library))
    return library


def test_build_embedder_uses_the_configured_provider(monkeypatch):
    loaded = []
    monkeypatch.setattr(literature_module, "AsyncSentenceTransformerEmbedder", lambda name: loaded.append(name) or name)

    assert build_embedder(EmbeddingsConfig(model="all-MiniLM-L6-v2")) == "all-MiniLM-L6-v2"
    assert loaded == ["all-MiniLM-L6-v2"]

    remote = build_embedder(EmbeddingsConfig(provider="openai", model="text-embedding-3-small", api_key="sk-test"))
    assert isinstance(remote, AsyncOpenAIEmbedder)
    asyncio.run(remote.aclose())


def test_build_chunker_follows_the_config():
    chunker = build_chunker(EmbeddingsConfig(chunk_words=120, overlap_words=20))

    assert (chunker.chunk_words, chunker.overlap_words) == (120, 20)


def test_galaxy_query_is_one_phrase():
    assert galaxy_query('  NGC 1052-DF2 "b" ') == '"NGC 1052-DF2 b"'


def test_paper_filters_only_constrain_chosen_values():
    assert paper_filters() == []
    assert paper_filters(["astro-ph.GA"], (2016, 2020)) == [
        MetadataFilter("categories", frozenset({"astro-ph.GA"})),
        RangeFilter("year", low=2016, high=2020),
    ]


def test_library_needs_both_semantic_components():
    with pytest.raises(ValueError, match="both an embedder and a vector store"):
        PaperLibrary(InMemoryTextSearchStore(), embedder=HashingEmbedder())


def test_semantic_library_embeds_chunks_and_indexes_text():
    library = build_library()

    assert library.semantic
    assert isinstance(library.memory_ingestor(build_chunker(EmbeddingsConfig()), print), AsyncCompositeIngestor)
    assert len(library.usage_sources) == 1
    filled(library)
    assert asyncio.run(library.count()) == 3
    assert asyncio.run(library.documents(["2601.00002"]))["2601.00002"].title == "A galaxy lacking dark matter"


def test_lexical_library_only_indexes_text():
    library = build_library(semantic=False)

    assert not library.semantic
    assert library.usage_sources == []
    assert isinstance(library.memory_ingestor(build_chunker(EmbeddingsConfig()), print), AsyncSearchIndexer)
    assert [type(source) for source in library.edge_sources()] == [MetadataEdgeSource]


def test_hybrid_search_returns_hits_facets_and_match_counts():
    library = filled(build_library())

    result = asyncio.run(library.search('"dark matter"'))

    assert result.query_text == '"dark matter"'
    assert [chip.text for chip in result.chips] == ["dark matter"]
    assert {hit.record_id for hit in result.hits} >= {"2601.00001", "2601.00002"}
    assert result.total_matched == 2
    assert result.degraded == ()
    assert result.graph is None
    assert [facet.key for facet in result.facets] == ["categories", "year"]
    assert dict(result.facets[1].counts) == {"2016": 1, "2018": 1}
    assert result.elapsed_ms >= 0


def test_filters_narrow_hits_and_facets():
    library = filled(build_library())

    result = asyncio.run(library.search("galax*", filters=paper_filters(years=(2017, 2030))))

    assert {hit.record_id for hit in result.hits} == {"2601.00002", "2601.00003"}
    assert result.total_matched == 2
    assert dict(result.facets[1].counts) == {"2016": 1, "2018": 1, "2024": 1}


def test_semantic_search_counts_its_hits():
    library = filled(build_library())

    result = asyncio.run(library.search("velocity dispersion", mode="semantic", top_k=2))

    assert result.total_matched == len(result.hits) == 2
    assert all(hit.lexical_rank is None for hit in result.hits)


def test_semantic_search_needs_embeddings():
    library = filled(build_library(semantic=False))

    with pytest.raises(SearchQueryError):
        asyncio.run(library.search("velocity", mode="semantic"))


def test_overview_lists_papers_years_and_categories():
    library = filled(build_library())

    assert asyncio.run(library.overview()) == LibraryOverview(
        papers=3,
        years=(2016, 2018, 2024),
        categories=(("astro-ph.GA", 3), ("astro-ph.CO", 1)),
    )


def test_related_papers_links_shared_authors_and_similar_text():
    library = filled(build_library())

    assert [type(source) for source in library.edge_sources()] == [EmbeddingEdgeSource, MetadataEdgeSource]
    graph = asyncio.run(library.related_papers("2601.00001"))

    assert graph.seed_record_id == "2601.00001"
    assert {node.record_id for node in graph.nodes} >= {"2601.00001", "2601.00002"}
    assert any(edge.kind == "metadata" for edge in graph.edges)


def test_related_papers_applies_filters_but_keeps_the_seed():
    library = filled(build_library(semantic=False))

    graph = asyncio.run(library.related_papers("2601.00001", paper_filters(years=(2020, 2030))))

    assert [node.record_id for node in graph.nodes] == ["2601.00001"]
    assert graph.edges == ()


def test_aclose_closes_every_closeable_that_can_close():
    store = RecordingStore()
    library = build_library(semantic=False, closeables=[store, object()])

    asyncio.run(library.aclose())

    assert store.closed
    assert library.closeables[0] is store


def test_open_paper_library_owns_what_it_builds(catalogue_config, monkeypatch):
    built = HashingEmbedder()
    monkeypatch.setattr(literature_module, "build_embedder", lambda _config: built)

    library = open_paper_library(catalogue_config)

    assert library.semantic
    assert isinstance(library.text_store, AsyncSqliteFts5Store)
    assert built in library.closeables
    assert len(library.closeables) == 3
    asyncio.run(library.aclose())
    assert built.closed


def test_open_paper_library_borrows_a_shared_embedder(catalogue_config):
    shared = HashingEmbedder()

    library = open_paper_library(catalogue_config, shared)

    assert shared not in library.closeables
    asyncio.run(library.aclose())
    assert not shared.closed


def test_open_paper_library_without_embeddings_opens_only_the_text_index(catalogue_config):
    config = catalogue_config.model_copy(update={"embeddings": EmbeddingsConfig(enabled=False)})

    library = open_paper_library(config)

    assert not library.semantic
    assert library.closeables == [library.text_store]
    asyncio.run(library.aclose())


def test_with_paper_library_runs_the_operation_and_closes(catalogue_config):
    shared = HashingEmbedder()

    async def index_and_search(library):
        await ingest_papers(library)
        return await library.search("dwarf", mode="lexical")

    result = with_paper_library(catalogue_config, index_and_search, shared)

    assert [hit.record_id for hit in result.hits] == ["2601.00003"]
    assert with_paper_library(catalogue_config, lambda library: library.count(), shared) == 3
