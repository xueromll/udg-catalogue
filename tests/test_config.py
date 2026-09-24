import warnings

import pytest
from sci_etl_core import ConfigurationError

from udg_catalogue.config import (
    API_KEY_ENV_VAR,
    DEFAULT_CONFIG_PATH,
    EMBEDDING_API_KEY_ENV_VAR,
    PROJECT_ROOT,
    CatalogueConfig,
    EmbeddingsConfig,
    embedding_key_missing,
    load_catalogue_config,
)


def test_repository_config_loads_with_project_relative_paths(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "sk-from-environment")

    config = load_catalogue_config()

    assert config.llm.api_key.get_secret_value() == "sk-from-environment"
    assert config.llm.base_url == "https://api.deepseek.com"
    assert config.pipeline.search_query == "cat:astro-ph.GA AND abs:ultra-diffuse"
    assert config.pipeline.total_limit == 500
    assert config.pipeline.max_concurrency == 6
    assert config.pipeline.newest_first
    assert config.embeddings.provider == "local"
    assert config.paths.raw_catalogue == PROJECT_ROOT / "udg_database.csv"
    assert config.paths.processed_ids == PROJECT_ROOT / "processed_arxiv_ids.txt"
    assert config.paths.search_index == PROJECT_ROOT / "paper_index.db"
    assert DEFAULT_CONFIG_PATH == PROJECT_ROOT / "config.yaml"


def test_repository_config_uses_no_deprecated_settings():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        load_catalogue_config()


def test_env_file_beside_config_supplies_api_key_and_paths_follow_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "pipeline:\n  total_limit: 42\npaths:\n  raw_catalogue: data/raw.csv\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(f"{API_KEY_ENV_VAR}=sk-from-dotenv\n", encoding="utf-8")

    config = load_catalogue_config(config_path)

    assert config.llm.api_key.get_secret_value() == "sk-from-dotenv"
    assert config.pipeline.total_limit == 42
    assert config.paths.raw_catalogue == tmp_path / "data" / "raw.csv"
    assert config.paths.sorted_catalogue == tmp_path / "udg_database_sorted.csv"
    assert config.paths.vector_memory == tmp_path / "paper_memory.db"


def test_embedding_api_key_comes_from_the_environment(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "embeddings:\n  provider: openai\n  model: text-embedding-3-small\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(EMBEDDING_API_KEY_ENV_VAR, "sk-embedding")

    config = load_catalogue_config(config_path)

    assert config.embeddings.api_key.get_secret_value() == "sk-embedding"
    assert config.embeddings.model == "text-embedding-3-small"
    assert "sk-embedding" not in repr(config)


def test_embedding_api_key_stays_empty_without_the_environment(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("embeddings:\n  enabled: false\n", encoding="utf-8")

    config = load_catalogue_config(config_path)

    assert config.embeddings.api_key.get_secret_value() == ""
    assert not config.embeddings.enabled


@pytest.mark.parametrize(
    ("embeddings", "missing"),
    [
        ({"provider": "openai"}, True),
        ({"provider": "openai", "api_key": "sk-embedding"}, False),
        ({"provider": "openai", "enabled": False}, False),
        ({"provider": "local"}, False),
    ],
)
def test_embedding_key_is_missing_only_for_an_enabled_remote_provider(embeddings, missing):
    config = CatalogueConfig(embeddings=EmbeddingsConfig(**embeddings))

    assert embedding_key_missing(config) is missing


def test_chunk_overlap_must_be_shorter_than_the_chunk(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("embeddings:\n  chunk_words: 50\n  overlap_words: 50\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="overlap_words must be smaller than chunk_words"):
        load_catalogue_config(config_path)


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
