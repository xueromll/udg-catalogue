"""sci-etl-core's exporter contract, run against the raw-catalogue CSV exporter the ingestion run writes."""

import csv

import pytest
from sci_etl_core.testing import ExporterContract

from udg_catalogue.config import KEY_COLUMN, MEASUREMENT_FIELDS
from udg_catalogue.pipeline import build_catalogue_exporter


def galaxies(record, count):
    return [
        {KEY_COLUMN: f"{record.record_id} galaxy {index}", **{field: float(index) for field in MEASUREMENT_FIELDS}}
        for index in range(count)
    ]


class TestCatalogueExporter(ExporterContract):
    @pytest.fixture
    def make_exporter(self, catalogue_config):
        return lambda: build_catalogue_exporter(catalogue_config)

    @pytest.fixture
    def make_entities(self):
        return galaxies

    @pytest.fixture
    def read_exported(self, catalogue_config):
        async def read(record_id):
            path = catalogue_config.paths.raw_catalogue
            if not path.is_file():
                return []
            with path.open(encoding="utf-8", newline="") as handle:
                return [tuple(row) for row in csv.reader(handle) if row[0] == record_id]

        return read
