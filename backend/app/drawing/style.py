"""Print styles for the raster and vector writers (mirrors the SVG export CSS)."""

from __future__ import annotations

from dataclasses import dataclass, replace

INK = "#1c1d21"
GREY = "#6b6a66"


@dataclass(frozen=True)
class Style:
    fill: str | None = None
    stroke: str | None = None
    width: float = 0.0  # metres at plan scale
    dash: tuple[float, float] | None = None
    text: str = INK
    bold: bool = False


BASE: dict[str, Style] = {
    "room": Style(),
    "zone-public": Style(fill="#f4ede0"),
    "zone-private": Style(fill="#e7efe6"),
    "zone-service": Style(fill="#e6ecf2"),
    "zone-circulation": Style(fill="#f2f1ee"),
    "wall": Style(fill=INK),
    "window": Style(fill="#ffffff", stroke=INK, width=0.014),
    "window-glass": Style(stroke=INK, width=0.01),
    "door-leaf": Style(stroke=INK, width=0.03),
    "door-swing": Style(stroke=INK, width=0.01),
    "door-garage": Style(stroke=INK, width=0.015, dash=(0.12, 0.08)),
    "boundary": Style(stroke="#9a978f", width=0.01, dash=(0.1, 0.08)),
    "fx": Style(fill="#ffffff", stroke=GREY, width=0.012),
    "fx-fill": Style(fill="#ecebe7", stroke=GREY, width=0.012),
    "fx-line": Style(stroke=GREY, width=0.01),
    "fx-thin": Style(stroke="#8d8b86", width=0.006),
    "fx-dash": Style(stroke="#8d8b86", width=0.008, dash=(0.06, 0.05)),
    "stair": Style(stroke=GREY, width=0.01),
    "stair-arrow": Style(stroke=INK, width=0.012),
    "stair-head": Style(fill=INK),
    "label-name": Style(text=INK, bold=True),
    "label-area": Style(text="#3d3c39"),
    "label-dim": Style(text=GREY),
    "label-note": Style(text=GREY),
    "dim": Style(stroke="#55534f", width=0.008),
    "dim-ext": Style(stroke="#55534f", width=0.008),
    "dim-tick": Style(stroke=INK, width=0.02),
    "dim-text": Style(text="#3d3c39"),
    "annot-line": Style(stroke=INK, width=0.012),
    "annot-fill": Style(fill=INK, stroke=INK, width=0.012),
    "annot-text": Style(text="#3d3c39"),
    "annot-title": Style(text=INK, bold=True),
}


def resolve(cls: str) -> Style:
    style = Style()
    for token in cls.split():
        s = BASE.get(token)
        if s is None:
            continue
        style = replace(
            style,
            fill=s.fill if s.fill is not None else style.fill,
            stroke=s.stroke if s.stroke is not None else style.stroke,
            width=s.width or style.width,
            dash=s.dash or style.dash,
            text=s.text if s.text != INK else style.text,
            bold=s.bold or style.bold,
        )
    return style


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
