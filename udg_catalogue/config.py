from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from sci_etl_core.config import BaseAppConfig, load_config

from udg_catalogue.prompts import PRESCREEN_CONCEPTS

if TYPE_CHECKING:
    from sci_etl_core.search import SqliteTuning

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
API_KEY_ENV_VAR = "DEEPSEEK_API_KEY"
EMBEDDING_API_KEY_ENV_VAR = "EMBEDDING_API_KEY"

KEY_COLUMN = "galaxy_name"
MEASUREMENT_FIELDS: tuple[str, ...] = (
    "ra",
    "dec",
    "distance_mpc",
    "effective_radius_kpc",
    "stellar_mass_solar",
    "dark_matter_fraction",
)
POSITION_FIELDS: tuple[str, ...] = ("ra", "dec")
PHYSICAL_FIELDS: tuple[str, ...] = tuple(field for field in MEASUREMENT_FIELDS if field not in POSITION_FIELDS)
MEASUREMENT_RANGES: dict[str, tuple[float, float]] = {
    "ra": (0.0, 360.0),
    "dec": (-90.0, 90.0),
    "distance_mpc": (0.0, 1e4),
    "effective_radius_kpc": (0.0, 100.0),
    "stellar_mass_solar": (0.0, 1e12),
    "dark_matter_fraction": (0.0, 1.0),
}
STRICTLY_POSITIVE_FIELDS: frozenset[str] = frozenset({"distance_mpc", "effective_radius_kpc", "stellar_mass_solar"})
PAPER_FACET_KEYS: tuple[str, ...] = ("categories", "authors", "year")
_STRICT = ConfigDict(extra="forbid")


class PathsConfig(BaseModel):
    model_config = _STRICT

    raw_catalogue: Path = Path("data/udg_database.csv")
    sorted_catalogue: Path = Path("data/udg_database_sorted.csv")
    processed_ids: Path = Path("data/processed_arxiv_ids.txt")
    pipeline_metadata: Path = Path("data/pipeline_meta.json")
    html_map: Path = Path("output/udg_3d_map.html")
    analytics_dir: Path = Path("output/figures")
    log_file: Path = Path("output/pipeline.log")
    search_index: Path = Path("data/paper_index.db")
    vector_memory: Path = Path("data/paper_memory.db")
    llm_cache: Path = Path("data/llm_cache.db")
    indexed_ids: Path = Path("data/indexed_arxiv_ids.txt")
    indexing_metadata: Path = Path("data/indexing_meta.json")
    rejections: Path = Path("data/rejected_galaxies.db")
    run_manifest: Path = Path("data/run_manifest.json")
    full_text_cache: Path = Path("data/full_text")

    def anchored_at(self, root: Path) -> PathsConfig:
        return self.model_copy(update={name: root / value for name, value in self})


class EmbeddingsConfig(BaseModel):
    model_config = _STRICT

    enabled: bool = True
    provider: Literal["local", "openai"] = "local"
    model: str = "all-MiniLM-L6-v2"
    base_url: str = "https://api.openai.com/v1"
    api_key: SecretStr = SecretStr("")
    chunk_words: int = Field(default=350, ge=2)
    overlap_words: int = Field(default=50, ge=0)

    @model_validator(mode="after")
    def _overlap_shorter_than_chunk(self) -> EmbeddingsConfig:
        if self.overlap_words >= self.chunk_words:
            raise ValueError("overlap_words must be smaller than chunk_words")
        return self


class SearchIndexConfig(BaseModel):
    """Memory given to the SQLite text index, as :class:`~sci_etl_core.search.SqliteTuning`.

    ``cache_size_mb`` is the page cache, ``mmap_size_mb`` the most of the index
    file read through a memory map. ``null`` keeps SQLite's default for that
    setting: a page cache of about 2 MB, and no memory map.
    """

    model_config = _STRICT

    cache_size_mb: int | None = Field(default=64, ge=0)
    mmap_size_mb: int | None = Field(default=None, ge=0)

    def to_tuning(self) -> SqliteTuning:
        from sci_etl_core.search import SqliteTuning

        return SqliteTuning(cache_size=_megabytes(self.cache_size_mb), mmap_size=_megabytes(self.mmap_size_mb))


def _megabytes(size: int | None) -> int | None:
    return None if size is None else size * 1024 * 1024


class PrescreenConfig(BaseModel):
    """An embedding filter run before the DeepSeek relevance check.

    When ``enabled``, a listing whose title and abstract score below
    ``threshold`` in cosine similarity against every one of ``concepts`` is
    judged not relevant without an LLM call. It is off by default because it
    can reject a paper the model would keep, which changes what the catalogue
    screens, and it needs ``embeddings.enabled``.
    """

    model_config = _STRICT

    enabled: bool = False
    threshold: float = Field(default=0.35, ge=-1.0, le=1.0, allow_inf_nan=False)
    concepts: list[str] = Field(default_factory=lambda: list(PRESCREEN_CONCEPTS), min_length=1)


class ArxivConfig(BaseModel):
    """How the pipeline paces arXiv requests (``udg_catalogue.arxiv.PoliteRateLimiter``).

    One request runs at a time, and each starts ``min_interval`` plus up to
    ``jitter`` seconds after the previous one ended. A 429 or 503 pauses every
    request for ``cooldown`` seconds, doubled for each further one, up to
    ``max_cooldown``.
    """

    model_config = _STRICT

    min_interval: float = Field(default=3.0, ge=0)
    jitter: float = Field(default=2.0, ge=0)
    cooldown: float = Field(default=60.0, ge=0)
    max_cooldown: float = Field(default=900.0, ge=0)


class ClusteringConfig(BaseModel):
    model_config = _STRICT

    max_distance_mpc: float = 5.0
    min_samples: int = 2


class DeduplicationConfig(BaseModel):
    """Sky matching, and the split of rows that share a name but not a position (``NamesakeSplitStep``)."""

    model_config = _STRICT

    max_separation_arcsec: float = 3.0
    namesake_separation_arcmin: float = Field(default=10.0, gt=0)
    namesake_distance_ratio: float = Field(default=1.5, ge=1.0)


class CatalogueConfig(BaseAppConfig):
    """The library's config sections plus the catalogue's own, with unknown keys rejected everywhere."""

    model_config = _STRICT

    paths: PathsConfig = Field(default_factory=PathsConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    search_index: SearchIndexConfig = Field(default_factory=SearchIndexConfig)
    prescreen: PrescreenConfig = Field(default_factory=PrescreenConfig)
    arxiv: ArxivConfig = Field(default_factory=ArxivConfig)
    clustering: ClusteringConfig = Field(default_factory=ClusteringConfig)
    deduplication: DeduplicationConfig = Field(default_factory=DeduplicationConfig)

    @model_validator(mode="after")
    def _prescreen_needs_embeddings(self) -> CatalogueConfig:
        if self.prescreen.enabled and not self.embeddings.enabled:
            raise ValueError("prescreen.enabled requires embeddings.enabled")
        return self


def embedding_key_missing(config: CatalogueConfig) -> bool:
    embeddings = config.embeddings
    return embeddings.enabled and embeddings.provider == "openai" and not embeddings.api_key.get_secret_value()


def load_catalogue_config(config_path: Path = DEFAULT_CONFIG_PATH) -> CatalogueConfig:
    resolved = Path(config_path).resolve()
    config = load_config(
        CatalogueConfig,
        resolved,
        resolved.parent / ".env",
        api_key_env_var=API_KEY_ENV_VAR,
    )
    update: dict[str, object] = {"paths": config.paths.anchored_at(resolved.parent)}
    embedding_key = os.getenv(EMBEDDING_API_KEY_ENV_VAR, "")
    if embedding_key:
        update["embeddings"] = config.embeddings.model_copy(update={"api_key": SecretStr(embedding_key)})
    return config.model_copy(update=update)
