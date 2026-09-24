import logging

import pytest
from sci_etl_core import EmbeddingError, PipelineAborted, PipelineInterrupted, ShutdownSignal

import main as entrypoint
from udg_catalogue.config import API_KEY_ENV_VAR

RAW_CATALOGUE = (
    "galaxy_name,ra,dec,distance_mpc,effective_radius_kpc,stellar_mass_solar,dark_matter_fraction\n"
    "Alpha,83.633,-5.361,5.0,2.0,1e8,0.9\n"
    "Beta,10.0,20.0,15.0,1.5,3e8,\n"
)
REPORT_NAMES = ["mass_vs_radius.png", "radius_dist.png", "stellar_mass_dist.png"]


async def ingestion_must_not_run(*_arguments):
    raise AssertionError("ingestion must not run")


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("pipeline:\n  total_limit: 3\n", encoding="utf-8")
    (tmp_path / "udg_database.csv").write_text(RAW_CATALOGUE, encoding="utf-8")
    monkeypatch.setattr(entrypoint, "configure_logging", lambda name, _log_file: logging.getLogger(f"test.{name}"))
    return tmp_path


def run_main(project, *arguments):
    return entrypoint.main(["--config", str(project / "config.yaml"), *arguments])


def test_skip_ingestion_rebuilds_every_output_offline(project, monkeypatch):
    monkeypatch.setattr(entrypoint, "run_ingestion", ingestion_must_not_run)

    assert run_main(project, "--skip-ingestion") == entrypoint.EXIT_OK

    assert (project / "udg_database_sorted.csv").is_file()
    assert (project / "udg_3d_map.html").is_file()
    assert sorted(path.name for path in (project / "analysis").iterdir()) == REPORT_NAMES


def test_missing_raw_catalogue_skips_reports(project, monkeypatch):
    monkeypatch.setattr(entrypoint, "run_ingestion", ingestion_must_not_run)
    (project / "udg_database.csv").unlink()

    assert run_main(project, "--skip-ingestion") == entrypoint.EXIT_OK

    assert not (project / "udg_database_sorted.csv").exists()
    assert not (project / "udg_3d_map.html").exists()


def test_missing_api_key_stops_before_ingestion(project, monkeypatch):
    monkeypatch.setattr(entrypoint, "run_ingestion", ingestion_must_not_run)

    assert run_main(project) == entrypoint.EXIT_MISSING_API_KEY

    assert not (project / "udg_database_sorted.csv").exists()


def test_ingestion_follows_the_config_unless_rescanning(project, monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "sk-test")
    calls = []

    async def record_ingestion(config, _logger, start_index, shutdown):
        calls.append((config.pipeline.total_limit, start_index, isinstance(shutdown, ShutdownSignal)))
        return 2

    monkeypatch.setattr(entrypoint, "run_ingestion", record_ingestion)
    monkeypatch.setattr(entrypoint, "run_paper_indexing", ingestion_must_not_run)

    assert run_main(project) == entrypoint.EXIT_OK
    assert run_main(project, "--rescan") == entrypoint.EXIT_OK

    assert calls == [(3, None, True), (3, 0, True)]
    assert (project / "udg_database_sorted.csv").is_file()


def test_index_papers_indexes_without_ingesting_or_rebuilding(project, monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "sk-test")
    calls = []

    async def record_indexing(_config, _logger, start_index, _shutdown):
        calls.append(start_index)
        return 5

    monkeypatch.setattr(entrypoint, "run_ingestion", ingestion_must_not_run)
    monkeypatch.setattr(entrypoint, "run_paper_indexing", record_indexing)

    assert run_main(project, "--index-papers", "--rescan") == entrypoint.EXIT_OK

    assert calls == [0]
    assert not (project / "udg_database_sorted.csv").exists()


def test_index_papers_and_skip_ingestion_are_exclusive(project):
    with pytest.raises(SystemExit):
        run_main(project, "--index-papers", "--skip-ingestion")


def test_missing_embedding_key_stops_before_ingestion(project, monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "sk-test")
    monkeypatch.setattr(entrypoint, "run_ingestion", ingestion_must_not_run)
    (project / "config.yaml").write_text("embeddings:\n  provider: openai\n", encoding="utf-8")

    assert run_main(project) == entrypoint.EXIT_MISSING_API_KEY

    assert not (project / "udg_database_sorted.csv").exists()


def test_interrupted_ingestion_stops_without_rebuilding(project, monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "sk-test")

    async def interrupt_ingestion(*_arguments):
        raise PipelineInterrupted("Run stopped by a shutdown request", 1)

    monkeypatch.setattr(entrypoint, "run_ingestion", interrupt_ingestion)

    assert run_main(project) == entrypoint.EXIT_INTERRUPTED

    assert not (project / "udg_database_sorted.csv").exists()


def test_unavailable_paper_memory_aborts_ingestion_but_rebuilds_outputs(project, monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "sk-test")

    async def fail_to_open_memory(*_arguments):
        raise EmbeddingError("sentence-transformers is required for local embedding")

    monkeypatch.setattr(entrypoint, "run_ingestion", fail_to_open_memory)

    assert run_main(project) == entrypoint.EXIT_INGESTION_ABORTED

    assert (project / "udg_database_sorted.csv").is_file()


def test_aborted_ingestion_still_rebuilds_outputs(project, monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "sk-test")

    async def abort_ingestion(*_arguments):
        raise PipelineAborted("Listing fetch failed", 4)

    monkeypatch.setattr(entrypoint, "run_ingestion", abort_ingestion)

    assert run_main(project) == entrypoint.EXIT_INGESTION_ABORTED

    assert (project / "udg_database_sorted.csv").is_file()
