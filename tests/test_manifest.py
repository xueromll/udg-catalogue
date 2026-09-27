import hashlib
import json
from datetime import UTC, datetime

from sci_etl_core.claims import content_hash

from udg_catalogue.manifest import MANIFEST_VERSION, build_manifest, write_manifest
from udg_catalogue.prompts import EXTRACTION_PROMPT, RELEVANCE_PROMPT

RAW = "record_id,galaxy_name,ra,dec,extra\n2401.00001,DF 44,195.24,26.98,\n2401.00002,DF 44,195.24,26.98,\n"
SORTED = "galaxy_name,source_papers,ra,dec\nDF 44,2401.00001; 2401.00002,195.24,26.98\n"


def fixed_clock():
    return datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def test_a_manifest_without_catalogue_files_records_nothing_built(catalogue_config):
    manifest = build_manifest(catalogue_config, now=fixed_clock)

    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["built_at"] == "2026-09-27T12:00:00+00:00"
    assert manifest["processed_arxiv_ids"] == []
    assert manifest["raw_catalogue"] == {"rows": 0, "sha256": None}
    assert manifest["sorted_catalogue"] == {"rows": 0, "sha256": None}


def test_the_manifest_describes_the_catalogues_and_what_produced_them(catalogue_config):
    paths = catalogue_config.paths
    paths.raw_catalogue.write_text(RAW, encoding="utf-8")
    paths.sorted_catalogue.write_text(SORTED, encoding="utf-8")
    paths.processed_ids.write_text("2401.00002\n\n2401.00001\n2401.00002\n", encoding="utf-8")
    messages = []

    destination = write_manifest(catalogue_config, messages.append)

    manifest = json.loads(destination.read_text(encoding="utf-8"))
    assert destination == paths.run_manifest
    assert manifest["software"]["sci-etl-core"]
    assert manifest["software"]["udg-catalogue"] is None
    assert manifest["llm"] == {"base_url": catalogue_config.llm.base_url, "model": catalogue_config.llm.model}
    assert manifest["prompts"] == {
        "relevance_sha256": content_hash(RELEVANCE_PROMPT),
        "extraction_sha256": content_hash(EXTRACTION_PROMPT),
    }
    assert manifest["query"] == catalogue_config.pipeline.search_query
    assert manifest["processed_arxiv_ids"] == ["2401.00001", "2401.00002"]
    assert manifest["raw_catalogue"] == {
        "rows": 2,
        "sha256": hashlib.sha256(paths.raw_catalogue.read_bytes()).hexdigest(),
    }
    assert manifest["sorted_catalogue"]["rows"] == 1
    assert messages == [f"Run manifest written to {destination}: 2 papers, 1 galaxies"]
    assert list(destination.parent.glob("*.tmp")) == []
