"""The CSS block for what Streamlit's theme file cannot express.

``.streamlit/config.toml`` carries the palette, the fonts and the 2 px radius.
This block adds the rest: mono for chips, identifiers and the
query bar, the persistent banner, 1 px borders without shadows, dimmed rows and
the quiet empty states. It is the only CSS in the app, and the only external
resource it loads is Google Fonts for Inter and JetBrains Mono, with system
fallbacks when they are unreachable.
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

FONTS_URL = "https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=JetBrains+Mono:wght@400;600&display=swap"


def theme_css() -> str:
    """Return the style sheet, built from the tokens so a palette change happens in one file."""
    return f"""
@import url('{FONTS_URL}');
:root {{
  --udg-canvas: {CANVAS}; --udg-ink: {INK}; --udg-accent: {ACCENT};
  --udg-separator: {SEPARATOR}; --udg-muted: {MUTED};
  --udg-mono: {FONT_MONO}; --udg-sans: {FONT_SANS};
}}
/* Type: sans for titles and body, mono with tabular figures for anything a user could paste. */
.udg-mono, .udg-chip, .udg-status, .udg-id, .udg-kv, .udg-meta, .udg-region,
[class*="st-key-query-bar"] input, [class*="st-key-facet-"] button {{
  font-family: var(--udg-mono); font-variant-numeric: tabular-nums; font-size: {TYPE_12}px;
}}
[class*="st-key-query-bar"] input {{ font-size: {TYPE_14}px; }}
.udg-title {{ font-family: var(--udg-sans); font-size: {TYPE_16}px; line-height: 26px; color: var(--udg-ink); }}
.udg-hit-title {{ font-family: var(--udg-sans); font-size: {TYPE_14}px; line-height: 22px; }}
/* Depth is a 1 px rule, never a shadow. */
[data-testid="stVerticalBlockBorderWrapper"], .stButton button, .stTextInput input, .stSelectbox > div {{
  box-shadow: none !important; border-radius: {RADIUS}px;
}}
/* Region headers: 12 px, secondary colour, one separator rule. */
.udg-region {{ color: var(--udg-muted); border-bottom: {BORDER_WIDTH}px solid var(--udg-separator);
  padding-bottom: 4px; margin: 0 0 {SPACE[0]}px 0; }}
/* Chips: parsed query terms with a solid border, active filters with a dashed one. */
.udg-chips {{ margin: 0 0 {SPACE[0]}px 0; }}
.udg-chip {{ display: inline-block; line-height: 22px; padding: 0 {SPACE[0]}px; margin: 0 {SPACE[0]}px 4px 0;
  border: {BORDER_WIDTH}px solid var(--udg-ink); border-radius: {RADIUS}px; color: var(--udg-ink); }}
.udg-chip-filter {{ border-style: dashed; }}
.udg-chip-negated {{ text-decoration: line-through; color: var(--udg-muted); border-color: var(--udg-muted); }}
.udg-status {{ color: var(--udg-ink); margin: 0 0 {SPACE[0]}px 0; }}
/* The banner is persistent: separator ground, 1 px ink rule below, a glyph per condition. */
.udg-banner {{ background: var(--udg-separator); border-bottom: {BORDER_WIDTH}px solid var(--udg-ink);
  padding: 4px {SPACE[0]}px; margin: 0 0 {SPACE[1]}px 0; font-size: {TYPE_14}px; color: var(--udg-ink); }}
.udg-banner-line {{ display: block; line-height: 24px; }}
.udg-banner-glyph {{ font-family: var(--udg-mono); display: inline-block; width: {SPACE[1]}px; }}
/* Secondary text, dimmed rows and quiet empty states. */
.udg-meta, .udg-quiet, .udg-dim {{ color: var(--udg-muted); }}
.udg-quiet {{ font-size: {TYPE_14}px; line-height: 22px; }}
/* The selected hit carries the one accent rule of the list. */
.udg-hit-selected {{ border-left: 2px solid var(--udg-accent); padding-left: 6px; }}
/* Facet rows: one left-aligned row per value, the selected row with the accent bar. */
[class*="st-key-facet-"] button {{ width: 100%; justify-content: flex-start; text-align: left; border: 0;
  padding: 0 {SPACE[0]}px; min-height: {SPACE[2]}px; transition: background {MOTION_STATE_MS}ms ease-out; }}
[class*="st-key-facet-"] button:hover {{ background: var(--udg-separator); }}
[class*="st-key-facet-on-"] button {{ border-left: 2px solid var(--udg-accent); border-radius: 0; }}
/* Key-value grid for the extraction stamp. */
.udg-kv {{ display: grid; grid-template-columns: 80px 1fr; row-gap: 4px; column-gap: {SPACE[0]}px; }}
"""


def style_tag() -> str:
    """The style sheet wrapped for ``st.html``."""
    return f"<style>{theme_css()}</style>"
