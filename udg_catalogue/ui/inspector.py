"""The inspector: one paper, the galaxies the catalogue took from it, its rejected extractions and the run's stamp."""

from __future__ import annotations

import html
import json
import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sci_etl_core.discovery import DiscoveryResult
from sci_etl_core.search import DiscoveryGraph

from udg_catalogue.config import KEY_COLUMN, MEASUREMENT_FIELDS
from udg_catalogue.paper_views import author_line, paper_url, publication_year

SOURCE_PAPERS_COLUMN = "source_papers"
RECORD_COLUMN = "record_id"
SOURCE_SEPARATOR = ";"
MEASURED_COLUMNS: tuple[str, ...] = (KEY_COLUMN, *MEASUREMENT_FIELDS)
VERSION_SUFFIX = re.compile(r"v\d+$")
NO_SOURCE_COLUMN = "The catalogue does not name its papers yet: it predates the source_papers column."
NO_GALAXIES = "No galaxy in the catalogue comes from this paper."
NO_REVIEW_STORE = "no review store in this workspace"
NO_MANIFEST = "no run manifest in this workspace"
STAMP_UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PaperCard:
    record_id: str
    title: str
    year: str
    categories: tuple[str, ...]
    authors: str

    @property
    def url(self) -> str:
        return paper_url(self.record_id)


def bare_id(record_id: str) -> str:
    """The arXiv id without a version suffix, so ``2301.04512v2`` matches ``2301.04512``."""
    return VERSION_SUFFIX.sub("", record_id.strip())


def paper_card(record_id: str, title: str, metadata: dict[str, Any]) -> PaperCard:
    categories = metadata.get("categories") or ()
    if isinstance(categories, str):
        categories = (categories,)
    return PaperCard(
        record_id,
        " ".join(title.split()) or record_id,
        publication_year(metadata),
        tuple(str(category) for category in categories),
        author_line(metadata),
    )


def find_paper(result: DiscoveryResult | None, graph: DiscoveryGraph | None, record_id: str) -> PaperCard | None:
    """The card for ``record_id`` from what is already on screen: the hits first, then the graph."""
    for hit in result.hits if result is not None else ():
        if hit.record_id == record_id:
            return paper_card(hit.record_id, hit.title, hit.metadata)
    for node in graph.nodes if graph is not None else ():
        if node.record_id == record_id:
            return paper_card(node.record_id, node.title, node.metadata)
    return None


def card_html(card: PaperCard) -> str:
    """Title in sans, id in mono and linked, authors and year in the secondary colour."""
    categories = html.escape(", ".join(card.categories)) if card.categories else "no category"
    authors = f'<div class="udg-meta">{html.escape(card.authors)}</div>' if card.authors else ""
    return (
        f'<div class="udg-id"><a href="{html.escape(card.url)}">{html.escape(card.record_id)}</a></div>'
        f'<div class="udg-title">{html.escape(card.title)}</div>{authors}'
        f'<div class="udg-meta">year {html.escape(card.year)} · {categories}</div>'
    )


def paper_ids(cell: Any) -> set[str]:
    """The record ids of one ``source_papers`` cell."""
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return set()
    return {bare_id(part) for part in str(cell).split(SOURCE_SEPARATOR) if part.strip()}


def galaxies_from_paper(catalogue: pd.DataFrame, record_id: str) -> tuple[pd.DataFrame, str]:
    """The catalogue rows that name ``record_id`` among their papers, with the measured columns, and a note when there are none."""
    wanted = bare_id(record_id)
    if SOURCE_PAPERS_COLUMN in catalogue.columns:
        mask = catalogue[SOURCE_PAPERS_COLUMN].map(lambda cell: wanted in paper_ids(cell))
    elif RECORD_COLUMN in catalogue.columns:
        mask = catalogue[RECORD_COLUMN].map(lambda cell: bare_id(str(cell)) == wanted)
    else:
        return catalogue.iloc[0:0], NO_SOURCE_COLUMN
    columns = [column for column in MEASURED_COLUMNS if column in catalogue.columns]
    rows = catalogue.loc[mask, columns].reset_index(drop=True)
    return rows, "" if len(rows) else NO_GALAXIES


def rejections_for(path: Path, record_id: str) -> list[dict[str, str]] | None:
    """The rejected extractions of ``record_id`` from the pipeline's review store, or ``None`` without a readable store."""
    if not path.is_file():
        return None
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            rows = connection.execute(
                "SELECT entity, violations, quote, created_at, resolution FROM rejections"
                " WHERE record_id = ? ORDER BY created_at",
                (record_id,),
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    return [rejection_row(*row) for row in rows]


def rejection_row(entity: str, violations: str, quote: str, created_at: str, resolution: str | None) -> dict[str, str]:
    fields = json.loads(entity)
    reasons = "; ".join(f"{item.get('field') or ''} {item.get('code') or ''}".strip() for item in json.loads(violations))
    return {
        "galaxy": str(fields.get(KEY_COLUMN) or json.dumps(fields, ensure_ascii=False)),
        "reasons": reasons,
        "quote": quote,
        "status": resolution or "unresolved",
        "rejected_at": created_at[:10],
    }


def load_manifest(path: Path) -> dict[str, Any] | None:
    """The run manifest beside the catalogue, or ``None`` when it is missing or not a JSON object."""
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


def extraction_stamp(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    """``(label, value)`` rows of the stamp: model, prompt hashes, library version and build date."""
    llm = manifest.get("llm") or {}
    prompts = manifest.get("prompts") or {}
    software = manifest.get("software") or {}
    library = software.get("sci-etl-core")
    return [
        ("model", str(llm.get("model") or STAMP_UNKNOWN)),
        ("prompt", str(prompts.get("extraction_sha256") or STAMP_UNKNOWN)[:8]),
        ("relevance", str(prompts.get("relevance_sha256") or STAMP_UNKNOWN)[:8]),
        ("library", f"sci-etl-core/{library}" if library else STAMP_UNKNOWN),
        ("built", str(manifest.get("built_at") or STAMP_UNKNOWN)[:10]),
    ]


def stamp_html(rows: Sequence[tuple[str, str]]) -> str:
    cells = "".join(f"<span>{html.escape(label)}</span><span>{html.escape(value)}</span>" for label, value in rows)
    return f'<div class="udg-kv">{cells}</div>'
