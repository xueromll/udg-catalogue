import warnings

import pytest
from pydantic import ValidationError
from sci_etl_core import ConfigurationError
from sci_etl_core.search import SqliteTuning

from udg_catalogue.config import (
    ArxivConfig,
    API_KEY_ENV_VAR,
    DEFAULT_CONFIG_PATH,
    EMBEDDING_API_KEY_ENV_VAR,
    PROJECT_ROOT,
    CatalogueConfig,
    EmbeddingsConfig,
    PrescreenConfig,
    SearchIndexConfig,
    embedding_key_missing,
    load_catalogue_config,
)
from udg_catalogue.prompts import PRESCREEN_CONCEPTS

MEBIBYTE = 1024 * 1024


def test_repository_config_loads_with_project_relative_paths(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "sk-from-environment")

    config = load_catalogue_config()

    assert config.llm.api_key.get_secret_value() == "sk-from-environment"
    assert config.llm.base_url == "https://api.deepseek.com"
    assert config.pipeline.search_query.startswith('cat:astro-ph* AND (ti:"ultra-diffuse" OR abs:"ultra-diffuse"')
    assert "\n" not in config.pipeline.search_query
    assert config.pipeline.total_limit == 2000
    assert config.pipeline.max_concurrency == 16
    assert config.arxiv == ArxivConfig(min_interval=3.0, jitter=2.0, cooldown=60.0, max_cooldown=900.0)
    assert config.paths.full_text_cache == PROJECT_ROOT / "data" / "full_text"
    assert config.pipeline.newest_first
    assert config.embeddings.provider == "local"
    assert config.search_index == SearchIndexConfig(cache_size_mb=64, mmap_size_mb=None)
    assert config.prescreen == PrescreenConfig(enabled=True, threshold=0.35)
    assert config.paths.raw_catalogue == PROJECT_ROOT / "data" / "udg_database.csv"
    assert config.paths.processed_ids == PROJECT_ROOT / "data" / "processed_arxiv_ids.txt"
    assert config.paths.search_index == PROJECT_ROOT / "data" / "paper_index.db"
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
    assert config.paths.sorted_catalogue == tmp_path / "data" / "udg_database_sorted.csv"
    assert config.paths.vector_memory == tmp_path / "data" / "paper_memory.db"


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


@pytest.mark.parametrize(
    ("yaml_text", "key"),
    [
        ("paths:\n  raw_catalog: data/x.csv\n", "paths.raw_catalog"),
        ("deduplication:\n  max_separation: 2.0\n", "deduplication.max_separation"),
        ("pipeline:\n  max_records: 10\n", "pipeline.max_records"),
        ("clustring:\n  min_samples: 3\n", "clustring"),
        ("search_index:\n  cache_mb: 8\n", "search_index.cache_mb"),
        ("prescreen:\n  enable: true\n", "prescreen.enable"),
    ],
)
def test_an_unknown_key_fails_validation_and_is_named(tmp_path, yaml_text, key):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(ConfigurationError, match=key.replace(".", r"\.")):
        load_catalogue_config(config_path)


def test_missing_config_file_raises_configuration_error(tmp_path):
    with pytest.raises(ConfigurationError):
        load_catalogue_config(tmp_path / "missing.yaml")


@pytest.mark.parametrize(
    ("settings", "tuning"),
    [
        ({}, SqliteTuning(cache_size=64 * MEBIBYTE, mmap_size=None)),
        ({"cache_size_mb": None, "mmap_size_mb": 0}, SqliteTuning(cache_size=None, mmap_size=0)),
        ({"cache_size_mb": 8, "mmap_size_mb": 256}, SqliteTuning(cache_size=8 * MEBIBYTE, mmap_size=256 * MEBIBYTE)),
    ],
)
def test_search_index_settings_become_sqlite_tuning_in_bytes(settings, tuning):
    assert SearchIndexConfig(**settings).to_tuning() == tuning


def test_search_index_sizes_must_not_be_negative():
    with pytest.raises(ValidationError, match="cache_size_mb"):
        SearchIndexConfig(cache_size_mb=-1)


def test_prescreen_is_off_by_default_and_screens_against_the_catalogue_concepts():
    prescreen = CatalogueConfig().prescreen

    assert not prescreen.enabled
    assert prescreen.threshold == 0.35
    assert prescreen.concepts == list(PRESCREEN_CONCEPTS)


def test_prescreen_needs_at_least_one_concept():
    with pytest.raises(ValidationError, match="concepts"):
        PrescreenConfig(concepts=[])


def test_prescreen_requires_embeddings(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("embeddings:\n  enabled: false\nprescreen:\n  enabled: true\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="prescreen.enabled requires embeddings.enabled"):
        load_catalogue_config(config_path)


def test_prescreen_loads_with_embeddings_enabled(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "prescreen:\n  enabled: true\n  threshold: 0.5\n  concepts:\n    - observed ultra-diffuse galaxies\n",
        encoding="utf-8",
    )

    prescreen = load_catalogue_config(config_path).prescreen

    assert prescreen == PrescreenConfig(enabled=True, threshold=0.5, concepts=["observed ultra-diffuse galaxies"])


def test_defaults_match_previous_pipeline_settings():
    config = CatalogueConfig()

    assert config.pipeline.page_size == 100
    assert config.pipeline.search_delay == 3.0
    assert config.clustering.max_distance_mpc == 5.0
    assert config.clustering.min_samples == 2
    assert config.deduplication.max_separation_arcsec == 3.0
    assert config.deduplication.namesake_separation_arcmin == 10.0
    assert config.deduplication.namesake_distance_ratio == 1.5
