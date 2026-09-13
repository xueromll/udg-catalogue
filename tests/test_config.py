import pytest
from sci_etl_core import ConfigurationError

from udg_catalogue.config import (
    API_KEY_ENV_VAR,
    DEFAULT_CONFIG_PATH,
    PROJECT_ROOT,
    CatalogueConfig,
    load_catalogue_config,
)


def test_repository_config_loads_with_project_relative_paths(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "sk-from-environment")

    config = load_catalogue_config()

    assert config.llm.api_key.get_secret_value() == "sk-from-environment"
    assert config.llm.base_url == "https://api.deepseek.com"
    assert config.pipeline.search_query == "cat:astro-ph.GA AND abs:ultra-diffuse"
    assert config.pipeline.max_records == 500
    assert config.paths.raw_catalogue == PROJECT_ROOT / "udg_database.csv"
    assert config.paths.processed_ids == PROJECT_ROOT / "processed_arxiv_ids.txt"
    assert DEFAULT_CONFIG_PATH == PROJECT_ROOT / "config.yaml"


def test_env_file_beside_config_supplies_api_key_and_paths_follow_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "pipeline:\n  max_records: 42\npaths:\n  raw_catalogue: data/raw.csv\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(f"{API_KEY_ENV_VAR}=sk-from-dotenv\n", encoding="utf-8")

    config = load_catalogue_config(config_path)

    assert config.llm.api_key.get_secret_value() == "sk-from-dotenv"
    assert config.pipeline.max_records == 42
    assert config.paths.raw_catalogue == tmp_path / "data" / "raw.csv"
    assert config.paths.sorted_catalogue == tmp_path / "udg_database_sorted.csv"


def test_missing_config_file_raises_configuration_error(tmp_path):
    with pytest.raises(ConfigurationError):
        load_catalogue_config(tmp_path / "missing.yaml")


def test_defaults_match_previous_pipeline_settings():
    config = CatalogueConfig()

    assert config.pipeline.page_size == 100
    assert config.pipeline.search_delay == 3.0
    assert config.clustering.max_distance_mpc == 5.0
    assert config.clustering.min_samples == 2
    assert config.deduplication.max_separation_arcsec == 3.0
