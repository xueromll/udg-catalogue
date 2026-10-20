from udg_catalogue.ui import tokens
from udg_catalogue.ui.theme import FONTS_URL, style_tag, theme_css


def test_rgba_converts_hex_and_keeps_a_short_alpha():
    assert tokens.rgba("#94A3B8", 0.4) == "rgba(148,163,184,0.4)"
    assert tokens.rgba("334155", 1.0) == "rgba(51,65,85,1)"


def test_ink_scale_runs_from_the_lightest_ramp_step_to_the_darkest():
    scale = tokens.ink_scale()

    assert len(scale) == len(tokens.COMMUNITY_RAMP) == 6
    assert scale[0] == [0.0, "#90A2BC"]
    assert scale[-1] == [1.0, "#263140"]


def test_plotly_layout_starts_from_the_canvas_and_accepts_overrides():
    layout = tokens.plotly_layout(height=120)

    assert layout["template"] == "none"
    assert layout["paper_bgcolor"] == layout["plot_bgcolor"] == tokens.CANVAS
    assert layout["title"] == {"text": None}
    assert layout["colorway"] == list(tokens.COMMUNITY_RAMP)
    assert layout["height"] == 120


def test_theme_css_is_built_from_the_tokens_without_shadows_or_gradients():
    css = theme_css()

    assert FONTS_URL in css
    assert tokens.INK in css and tokens.ACCENT in css and tokens.FONT_MONO in css
    assert ".udg-chip-filter { border-style: dashed; }" in css
    assert "gradient" not in css
    assert css.count("box-shadow") == css.count("box-shadow: none")
    assert style_tag() == f"<style>{css}</style>"
