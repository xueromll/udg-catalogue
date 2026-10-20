"""Design tokens of the slate visual system, as the desk brief fixes them.

Values are copied from ``sci-etl-internal/ecosystem/ui/02-pure-python-native.md``,
section 6. Everything that draws a colour, a font or a size reads it from here.
"""

from __future__ import annotations

from typing import Any

CANVAS = "#F4F5F7"  # 60 %: page, panels, chart background
INK = "#334155"  # 30 %: type, borders, node strokes
ACCENT = "#6366F1"  # 10 %: the selection class only (seed node, primary action, selected facet)
SEPARATOR = "#E2E5EA"  # panel separators, hover rows, banner ground, graph edges
MUTED = "#94A3B8"  # secondary text, dimmed nodes
HALO = "#C7D2FE"  # selection halo
COMMUNITY_RAMP: tuple[str, ...] = ("#263140", "#334155", "#43566F", "#566E90", "#7088A9", "#90A2BC")
DIMMED_ALPHA = 0.4

FONT_MONO = "JetBrains Mono, IBM Plex Mono, SFMono-Regular, Menlo, Consolas, monospace"
FONT_SANS = "Inter, -apple-system, Segoe UI, Roboto, system-ui, sans-serif"
TYPE_12 = 12
TYPE_14 = 14
TYPE_16 = 16
SPACE: tuple[int, ...] = (8, 16, 24, 32, 40, 48)
BORDER_WIDTH = 1
RADIUS = 2
MOTION_STATE_MS = 120


def rgba(hex_colour: str, alpha: float) -> str:
    """Return ``#rrggbb`` as a CSS ``rgba()`` string with ``alpha`` in [0, 1]."""
    value = hex_colour.lstrip("#")
    red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    return f"rgba({red},{green},{blue},{alpha:g})"


def ink_scale() -> list[list[float | str]]:
    """A continuous Plotly colour scale from the lightest ramp step to the darkest."""
    steps = tuple(reversed(COMMUNITY_RAMP))
    last = len(steps) - 1
    return [[index / last, colour] for index, colour in enumerate(steps)]


def plotly_layout(**overrides: Any) -> dict[str, Any]:
    """The layout every chart of the app starts from: canvas ground, ink type, no title, no shadows."""
    layout: dict[str, Any] = {
        "template": "none",
        "paper_bgcolor": CANVAS,
        "plot_bgcolor": CANVAS,
        "font": {"family": FONT_SANS, "color": INK, "size": TYPE_12},
        "title": {"text": None},
        "colorway": list(COMMUNITY_RAMP),
        "margin": {"l": SPACE[0], "r": SPACE[0], "t": SPACE[0], "b": SPACE[0]},
        "hoverlabel": {
            "bgcolor": CANVAS,
            "bordercolor": INK,
            "font": {"family": FONT_MONO, "color": INK, "size": TYPE_12},
        },
        "legend": {
            "bgcolor": CANVAS,
            "borderwidth": 0,
            "font": {"family": FONT_MONO, "color": INK, "size": TYPE_12},
        },
    }
    layout.update(overrides)
    return layout
