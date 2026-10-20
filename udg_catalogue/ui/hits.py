"""The result list: one row per fused hit, title in sans, id, ranks and score in mono."""

from __future__ import annotations

import html

from sci_etl_core.search import FusedHit

from udg_catalogue.paper_views import paper_url, publication_year


def rank_label(hit: FusedHit) -> str:
    """``L1 S3`` as the mockup writes the two legs' ranks, ``-`` for a leg that did not return the hit."""
    lexical = "-" if hit.lexical_rank is None else hit.lexical_rank
    semantic = "-" if hit.semantic_rank is None else hit.semantic_rank
    return f"L{lexical} S{semantic}"


def hit_html(position: int, hit: FusedHit, selected: str | None = None) -> str:
    """The row's header: rank and linked title, then id, year, leg ranks and fused score in mono."""
    title = html.escape(" ".join(hit.title.split()) or hit.record_id)
    marker = ' class="udg-hit-selected"' if hit.record_id == selected else ""
    return (
        f"<div{marker}>"
        f'<div class="udg-hit-title">{position}. <a href="{html.escape(paper_url(hit.record_id))}">{title}</a></div>'
        f'<div class="udg-meta">{html.escape(hit.record_id)} · {html.escape(publication_year(hit.metadata))}'
        f" · {rank_label(hit)} · {hit.score:.3f}</div></div>"
    )
