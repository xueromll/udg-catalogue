from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from sci_etl_core.config import BaseAppConfig, PipelineConfig, load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
API_KEY_ENV_VAR = "DEEPSEEK_API_KEY"

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


class CataloguePipelineConfig(PipelineConfig):
    page_size: int = 100
    search_delay: float = 3.0


class PathsConfig(BaseModel):
    raw_catalogue: Path = Path("udg_database.csv")
    sorted_catalogue: Path = Path("udg_database_sorted.csv")
    processed_ids: Path = Path("processed_arxiv_ids.txt")
    pipeline_metadata: Path = Path("pipeline_meta.json")
    html_map: Path = Path("udg_3d_map.html")
    analytics_dir: Path = Path("analysis")
    log_file: Path = Path("pipeline.log")

    def anchored_at(self, root: Path) -> PathsConfig:
        return self.model_copy(update={name: root / value for name, value in self})


class ClusteringConfig(BaseModel):
    max_distance_mpc: float = 5.0
    min_samples: int = 2


class DeduplicationConfig(BaseModel):
    max_separation_arcsec: float = 3.0


class CatalogueConfig(BaseAppConfig):
    pipeline: CataloguePipelineConfig = Field(default_factory=CataloguePipelineConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    clustering: ClusteringConfig = Field(default_factory=ClusteringConfig)
    deduplication: DeduplicationConfig = Field(default_factory=DeduplicationConfig)


def load_catalogue_config(config_path: Path = DEFAULT_CONFIG_PATH) -> CatalogueConfig:
    resolved = Path(config_path).resolve()
    config = load_config(
        CatalogueConfig,
        resolved,
        resolved.parent / ".env",
        api_key_env_var=API_KEY_ENV_VAR,
    )
    return config.model_copy(update={"paths": config.paths.anchored_at(resolved.parent)})
