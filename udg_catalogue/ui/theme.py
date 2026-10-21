"""The CSS block for what Streamlit's theme file cannot express.

``.streamlit/config.toml`` carries the palette, the fonts and the square corners.
This block lays the page out as an early-2000s bulletin board: a ruled site
header, a breadcrumb, every section a ruled board under an ink category bar,
striped rows, a statistics box and a footer. It also sets mono for chips,
identifiers and the query bar, the persistent banner, dimmed rows and the quiet
empty states. It is the only CSS in the app, and the only external resource it
loads is Google Fonts for JetBrains Mono, with the system mono as fallback
when it is unreachable.
"""

from __future__ import annotations

from udg_catalogue.ui.tokens import (
    ACCENT,
    BORDER_WIDTH,
    CANVAS,
    FONT_MONO,
    FONT_SANS,
    INK,
    MOTION_STATE_MS,
    MUTED,
    RADIUS,
    SEPARATOR,
    SPACE,
    TYPE_12,
    TYPE_14,
    TYPE_16,
)

FONTS_URL = "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap"
BAR_HEIGHT = 26


def theme_css() -> str:
    """Return the style sheet, built from the tokens so a palette change happens in one file."""
    rule = f"{BORDER_WIDTH}px solid var(--udg-ink)"
    return f"""
@import url('{FONTS_URL}');
:root {{
  --udg-canvas: {CANVAS}; --udg-ink: {INK}; --udg-accent: {ACCENT};
  --udg-separator: {SEPARATOR}; --udg-muted: {MUTED};
  --udg-mono: {FONT_MONO}; --udg-sans: {FONT_SANS};
}}
/* Type: Verdana for the board, mono with tabular figures for anything a user could paste. */
.udg-mono, .udg-chip, .udg-status, .udg-id, .udg-kv, .udg-meta,
[class*="st-key-query-bar"] input, [class*="st-key-facet-"] button {{
  font-family: var(--udg-mono); font-variant-numeric: tabular-nums; font-size: {TYPE_12}px;
}}
[class*="st-key-query-bar"] input {{ font-size: {TYPE_14}px; }}
.udg-title {{ font-family: var(--udg-sans); font-size: {TYPE_16}px; line-height: 26px; color: var(--udg-ink); }}
.udg-hit-title {{ font-family: var(--udg-sans); font-size: {TYPE_14}px; line-height: 22px; font-weight: 700; }}
a {{ color: var(--udg-ink); }}
a:hover {{ color: var(--udg-accent); }}
/* Depth is a 1 px rule, never a shadow. */
[data-testid="stVerticalBlockBorderWrapper"], .stButton button, .stTextInput input, .stSelectbox > div {{
  box-shadow: none !important; border-radius: {RADIUS}px;
}}
.stMainBlockContainer {{ padding-top: 72px; padding-bottom: {SPACE[3]}px; }}
[data-testid="stMarkdownContainer"]:has(> div, > table),
[class*="st-key-board-"] [data-testid="stHeading"] [data-testid="stMarkdownContainer"] {{ margin-bottom: 0; }}
.st-key-site-header [data-testid="stHeaderActionElements"] {{ display: none; }}
/* Site header: the board's name and tagline in a ruled box under a heavy ink rule. */
.st-key-site-header {{ border: {rule}; border-top-width: 4px; background: var(--udg-canvas);
  padding: {SPACE[1]}px {SPACE[2]}px; gap: 2px; }}
.st-key-site-header h1 {{ font-size: 22px; line-height: 30px; padding: 0; letter-spacing: -0.01em; }}
.udg-tagline {{ color: var(--udg-muted); font-size: {TYPE_12}px; }}
/* Breadcrumb: bold crumbs, the current page in plain ink, separators in the secondary colour. */
.udg-crumbs {{ font-size: {TYPE_12}px; font-weight: 700; color: var(--udg-ink); padding: 4px 0 {SPACE[0]}px; }}
.udg-crumb {{ color: var(--udg-muted); }}
.udg-crumb-here {{ color: var(--udg-ink); }}
.udg-crumb-sep {{ color: var(--udg-muted); font-weight: 400; padding: 0 6px; }}
/* Boards: a 1 px ink rule around each section, its first row an ink category bar. */
[class*="st-key-board-"], [class*="st-key-block-"], [data-testid="stExpander"] details {{
  border: {rule}; border-radius: {RADIUS}px; background: var(--udg-canvas);
}}
[class*="st-key-board-"], [class*="st-key-block-"] {{ padding: 0 {SPACE[0]}px {SPACE[0]}px; gap: {SPACE[0]}px; }}
.udg-region, [class*="st-key-board-"] h3, [data-testid="stExpander"] summary {{
  display: block; background: var(--udg-ink); color: var(--udg-canvas); font-family: var(--udg-sans);
  font-size: {TYPE_12}px; font-weight: 700; line-height: {BAR_HEIGHT}px; min-height: {BAR_HEIGHT}px;
  padding: 0 {SPACE[0]}px; border-radius: 0; letter-spacing: 0.02em;
}}
[class*="st-key-board-"] .udg-region, [class*="st-key-block-"] .udg-region, [class*="st-key-board-"] h3 {{
  margin: 0 -{SPACE[0]}px;
}}
.udg-region {{ margin: 0 0 {SPACE[0]}px 0; }}
[class*="st-key-board-"] [data-testid="stHeaderActionElements"] {{ display: none; }}
[data-testid="stExpander"] summary {{ display: flex; padding: 0 {SPACE[0]}px; }}
[data-testid="stExpander"] summary:hover {{ color: var(--udg-canvas); }}
[data-testid="stExpander"] summary p {{ font-size: {TYPE_12}px; font-weight: 700; }}
[data-testid="stExpander"] summary svg {{ color: var(--udg-canvas); fill: var(--udg-canvas); }}
/* Buttons: a ruled face on the separator ground, bold labels, the accent on hover. */
.stButton button, .stDownloadButton button {{ border: {rule}; background: var(--udg-separator);
  color: var(--udg-ink); font-weight: 700; transition: color {MOTION_STATE_MS}ms ease-out, border-color {MOTION_STATE_MS}ms ease-out; }}
.stButton button p, .stDownloadButton button p {{ font-size: {TYPE_12}px; font-weight: 700; }}
.stButton button:hover, .stDownloadButton button:hover {{ border-color: var(--udg-accent); color: var(--udg-accent); }}
.stButton button[kind="primary"] {{ background: var(--udg-accent); border-color: var(--udg-accent); color: var(--udg-canvas); }}
.stButton button[kind="tertiary"] {{ background: transparent; border-color: transparent; }}
/* Chips: parsed query terms with a solid border, active filters with a dashed one. */
.udg-chips {{ margin: 0 0 {SPACE[0]}px 0; }}
.udg-chip {{ display: inline-block; line-height: 22px; padding: 0 {SPACE[0]}px; margin: 0 {SPACE[0]}px 4px 0;
  border: {rule}; border-radius: {RADIUS}px; color: var(--udg-ink); }}
.udg-chip-filter {{ border-style: dashed; }}
.udg-chip-negated {{ text-decoration: line-through; color: var(--udg-muted); border-color: var(--udg-muted); }}
.udg-status {{ color: var(--udg-ink); margin: 0 0 {SPACE[0]}px 0; }}
/* The banner is persistent: separator ground, 1 px ink rule below, a glyph per condition. */
.udg-banner {{ background: var(--udg-separator); border-bottom: {rule};
  padding: 4px {SPACE[0]}px; margin: 0 0 {SPACE[1]}px 0; font-size: {TYPE_14}px; color: var(--udg-ink); }}
.udg-banner-line {{ display: block; line-height: 24px; }}
.udg-banner-glyph {{ font-family: var(--udg-mono); display: inline-block; width: {SPACE[1]}px; }}
/* Secondary text, dimmed rows and quiet empty states. */
.udg-meta, .udg-quiet, .udg-dim {{ color: var(--udg-muted); }}
.udg-quiet {{ font-size: {TYPE_14}px; line-height: 22px; }}
/* The hit list is a topic list: one ruled row per hit, striped, the selected one with the accent rule. */
[class*="st-key-topic-"] {{ border: 1px solid var(--udg-separator); border-top: 0; padding: 6px {SPACE[0]}px; gap: 2px; }}
[class*="st-key-topic-"]:nth-child(even of [class*="st-key-topic-"]) {{ background: var(--udg-separator); }}
.udg-hit-selected {{ border-left: 2px solid var(--udg-accent); padding-left: 6px; }}
/* Facet rows: one left-aligned row per value, the selected row with the accent bar. */
[class*="st-key-facet-"] button {{ width: 100%; justify-content: flex-start; text-align: left; border: 0;
  padding: 0 {SPACE[0]}px; min-height: {SPACE[2]}px; transition: background {MOTION_STATE_MS}ms ease-out; }}
[class*="st-key-facet-"] button:hover {{ background: var(--udg-separator); }}
[class*="st-key-facet-on-"] button {{ border-left: 2px solid var(--udg-accent); border-radius: 0; }}
/* Key-value grid for the extraction stamp. */
.udg-kv {{ display: grid; grid-template-columns: 80px 1fr; row-gap: 4px; column-gap: {SPACE[0]}px; }}
/* Nav strip under the site header: view links on the left, the time on the right. */
.udg-navbar {{ display: flex; justify-content: space-between; gap: {SPACE[1]}px; font-size: {TYPE_12}px;
  border-top: 1px solid var(--udg-separator); margin-top: {SPACE[0]}px; padding-top: 6px; }}
.udg-navbar a {{ font-weight: 700; text-decoration: none; }}
.udg-navbar a:hover {{ text-decoration: underline; }}
.udg-nav-here {{ font-weight: 700; color: var(--udg-accent); }}
.udg-now {{ color: var(--udg-muted); }}
/* Board index: forum tables with an ink head, striped rows, lamps and right-aligned counts. */
table.udg-forumline {{ width: 100%; table-layout: fixed; border-collapse: collapse; border: {rule}; font-size: {TYPE_12}px; margin: 0; }}
table.udg-forumline th:nth-child(2) {{ width: 26%; }}
table.udg-forumline th.udg-num {{ width: 68px; }}
table.udg-forumline td {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
table.udg-forumline th {{ background: var(--udg-ink); color: var(--udg-canvas); text-align: left; font-weight: 700;
  height: {BAR_HEIGHT}px; padding: 0 {SPACE[0]}px; border: 0; white-space: nowrap; }}
table.udg-forumline td {{ padding: 5px {SPACE[0]}px; border: 0; border-top: 1px solid var(--udg-separator); }}
table.udg-forumline tbody tr:nth-child(even) td {{ background: var(--udg-separator); }}
table.udg-forumline .udg-num {{ text-align: right; font-family: var(--udg-mono); font-variant-numeric: tabular-nums; }}
table.udg-forumline .udg-lamp {{ width: {SPACE[2]}px; text-align: center; padding-right: 0; }}
.udg-board-name {{ font-weight: 700; }}
.udg-nearest {{ font-family: var(--udg-mono); color: var(--udg-muted); }}
.udg-more td {{ color: var(--udg-muted); font-style: italic; }}
.udg-legend {{ font-size: 11px; color: var(--udg-muted); padding: 4px 2px 0; }}
.udg-legend .udg-lamp {{ color: var(--udg-ink); margin: 0 4px 0 {SPACE[1]}px; }}
.udg-legend .udg-lamp:first-child {{ margin-left: 0; }}
/* Statistics box and footer. */
.udg-stats-row {{ font-size: {TYPE_12}px; line-height: 22px; padding: 0 2px; }}
.udg-stats-row:nth-child(even) {{ background: var(--udg-separator); }}
.udg-footer {{ text-align: center; color: var(--udg-muted); font-size: 11px; padding: {SPACE[0]}px 0; }}
"""


def style_tag() -> str:
    """The style sheet wrapped for ``st.html``."""
    return f"<style>{theme_css()}</style>"
