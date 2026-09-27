"""A record of what produced the published catalogue: library, model, prompts, query, and papers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from sci_etl_core.claims import content_hash

from udg_catalogue.config import CatalogueConfig
from udg_catalogue.prompts import EXTRACTION_PROMPT, RELEVANCE_PROMPT

MANIFEST_VERSION = 1


def file_sha256(path: Path) -> str | None:
    """Return the SHA-256 hex digest of a file, or ``None`` when it does not exist."""
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def processed_ids(path: Path) -> list[str]:
    """Return the sorted arXiv ids the state file lists as processed."""
    if not path.is_file():
        return []
    return sorted({line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()})


def count_rows(path: Path) -> int:
    """Return the number of data rows in a CSV file, or 0 when it does not exist."""
    if not path.is_file():
        return 0
    import pandas as pd

    return len(pd.read_csv(path, dtype=str, keep_default_na=False))


def _installed(distribution: str) -> str | None:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def build_manifest(config: CatalogueConfig, now: Callable[[], datetime] | None = None) -> dict[str, Any]:
    """Describe the catalogue files on disk and everything that produced them."""
    paths = config.paths
    clock = now or (lambda: datetime.now(UTC))
    return {
        "manifest_version": MANIFEST_VERSION,
        "built_at": clock().isoformat(),
        "software": {
            "sci-etl-core": _installed("sci-etl-core"),
            "udg-catalogue": _installed("udg-catalogue"),
        },
        "llm": {"base_url": config.llm.base_url, "model": config.llm.model},
        "prompts": {
            "relevance_sha256": content_hash(RELEVANCE_PROMPT),
            "extraction_sha256": content_hash(EXTRACTION_PROMPT),
        },
        "query": config.pipeline.search_query,
        "processed_arxiv_ids": processed_ids(paths.processed_ids),
        "raw_catalogue": {"rows": count_rows(paths.raw_catalogue), "sha256": file_sha256(paths.raw_catalogue)},
        "sorted_catalogue": {
            "rows": count_rows(paths.sorted_catalogue),
            "sha256": file_sha256(paths.sorted_catalogue),
        },
    }


def write_manifest(config: CatalogueConfig, log: Callable[[str], None]) -> Path:
    """Write the manifest beside the published catalogue and return its path."""
    destination = config.paths.run_manifest
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(config)
    staging = destination.with_name(f"{destination.name}.tmp")
    staging.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    staging.replace(destination)
    log(
        f"Run manifest written to {destination}: {len(manifest['processed_arxiv_ids'])} papers, "
        f"{manifest['sorted_catalogue']['rows']} galaxies"
    )
    return destination
