import matplotlib
import pytest

from udg_catalogue.config import API_KEY_ENV_VAR, EMBEDDING_API_KEY_ENV_VAR, CatalogueConfig

matplotlib.use("Agg")


@pytest.fixture(autouse=True)
def isolated_api_key(monkeypatch):
    for name in (API_KEY_ENV_VAR, EMBEDDING_API_KEY_ENV_VAR):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


@pytest.fixture
def catalogue_config(tmp_path):
    (tmp_path / "data").mkdir()
    config = CatalogueConfig()
    return config.model_copy(update={"paths": config.paths.anchored_at(tmp_path)})


@pytest.fixture
def ingestion_config(catalogue_config):
    pipeline = catalogue_config.pipeline.model_copy(
        update={"search_delay": 0.0, "sleep_between": 0.0, "page_size": 2, "total_limit": 10}
    )
    return catalogue_config.model_copy(update={"pipeline": pipeline})
