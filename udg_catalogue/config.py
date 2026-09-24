from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from sci_etl_core.config import BaseAppConfig, load_config

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
FRACTION_BOUNDS: dict[str, tuple[float, float]] = {"dark_matter_fraction": (0.0, 1.0)}
PAPER_FACET_KEYS: tuple[str, ...] = ("categories", "authors", "year")


class PathsConfig(BaseModel):
    raw_catalogue: Path = Path("udg_database.csv")
    sorted_catalogue: Path = Path("udg_database_sorted.csv")
    processed_ids: Path = Path("processed_arxiv_ids.txt")
    pipeline_metadata: Path = Path("pipeline_meta.json")
    html_map: Path = Path("udg_3d_map.html")
    analytics_dir: Path = Path("analysis")
    log_file: Path = Path("pipeline.log")
    search_index: Path = Path("paper_index.db")
    vector_memory: Path = Path("paper_memory.db")
    llm_cache: Path = Path("llm_cache.db")
    indexed_ids: Path = Path("indexed_arxiv_ids.txt")
    indexing_metadata: Path = Path("indexing_meta.json")

    def anchored_at(self, root: Path) -> PathsConfig:
        return self.model_copy(update={name: root / value for name, value in self})


class EmbeddingsConfig(BaseModel):
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


class ClusteringConfig(BaseModel):
    max_distance_mpc: float = 5.0
    min_samples: int = 2


class DeduplicationConfig(BaseModel):
    max_separation_arcsec: float = 3.0


class CatalogueConfig(BaseAppConfig):
    paths: PathsConfig = Field(default_factory=PathsConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    clustering: ClusteringConfig = Field(default_factory=ClusteringConfig)
    deduplication: DeduplicationConfig = Field(default_factory=DeduplicationConfig)


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
