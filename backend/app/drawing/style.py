"""Print styles shared by the SVG, PDF and PNG writers.

Mirrors the screen palette in ``frontend/src/styles/tokens.css`` (light
theme): ivory-black ink, Le Corbusier Polychromie tints for zones and orange
vif for the one accent. Exports stay on white paper.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

INK = "#14181c"
INK_2 = "#4b5459"
GREY = "#6c7579"
LIGHT = "#8f989c"
ACCENT = "#b3401b"
PAPER = "#ffffff"


@dataclass(frozen=True)
class Style:
    fill: str | None = None
    stroke: str | None = None
    width: float = 0.0  # drawing units (metres at plan scale)
    dash: tuple[float, float] | None = None
    text: str = INK
    bold: bool = False
    spacing: float = 0.0  # letter spacing in em (SVG only)


BASE: dict[str, Style] = {
    "room": Style(),
    "zone-public": Style(fill="#f6e4cd"),
    "zone-private": Style(fill="#dfe7d7"),
    "zone-service": Style(fill="#d8e2e4"),
    "zone-circulation": Style(fill="#ebe9e2"),
    "wall": Style(fill=INK),
    "window": Style(fill=PAPER, stroke=INK, width=0.014),
    "window-glass": Style(stroke=INK, width=0.01),
    "door-leaf": Style(stroke=INK, width=0.03),
    "door-swing": Style(stroke=INK, width=0.008),
    "door-garage": Style(stroke=INK, width=0.015, dash=(0.12, 0.08)),
    "boundary": Style(stroke=LIGHT, width=0.01, dash=(0.1, 0.08)),
    "fx": Style(fill=PAPER, stroke=GREY, width=0.012),
    "fx-fill": Style(fill="#ebe7dd", stroke=GREY, width=0.012),
    "fx-line": Style(stroke=GREY, width=0.01),
    "fx-thin": Style(stroke=LIGHT, width=0.006),
    "fx-dash": Style(stroke=LIGHT, width=0.008, dash=(0.06, 0.05)),
    "stair": Style(stroke=GREY, width=0.01),
    "stair-arrow": Style(stroke=INK, width=0.012),
    "stair-head": Style(fill=INK),
    "label-name": Style(text=INK, bold=True, spacing=0.06),
    "label-area": Style(text=INK_2),
    "label-dim": Style(text=GREY),
    "label-note": Style(text=GREY),
    "dim": Style(stroke="#5b6468", width=0.008),
    "dim-ext": Style(stroke="#5b6468", width=0.008),
    "dim-tick": Style(stroke=INK, width=0.02),
    "dim-text": Style(text=INK_2),
    "annot-line": Style(stroke=INK, width=0.012),
    "annot-fill": Style(fill=INK, stroke=INK, width=0.012),
    "annot-text": Style(text=INK_2),
    "annot-title": Style(text=INK, bold=True, spacing=0.14),
    # Title block (see titleblock.py).
    "tb-frame": Style(fill=PAPER, stroke=INK, width=0.025),
    "tb-rule": Style(stroke=INK, width=0.012),
    "tb-mark": Style(fill=PAPER, stroke=INK, width=0.08),
    "tb-mark-line": Style(stroke=INK, width=0.05),
    "tb-mark-room": Style(fill=ACCENT),
    "tb-brand": Style(text=INK, bold=True),
    "tb-label": Style(text=GREY, bold=True, spacing=0.12),
    "tb-title": Style(text=INK, bold=True),
    "tb-text": Style(text=INK_2),
    "tb-accent": Style(text=ACCENT, bold=True, spacing=0.08),
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
            spacing=s.spacing or style.spacing,
        )
    return style


def css(font: str) -> str:
    """The same styles as a stylesheet for standalone SVG exports."""
    rules = [f"text {{ font-family: {font}; }}", f".bg {{ fill: {PAPER}; }}"]
    for cls, s in BASE.items():
        decl: list[str] = []
        if s.fill:
            decl.append(f"fill: {s.fill}")
        elif s.stroke:
            decl.append("fill: none")
        if s.stroke:
            decl += [f"stroke: {s.stroke}", f"stroke-width: {s.width:g}"]
        if s.dash:
            decl.append(f"stroke-dasharray: {s.dash[0]:g} {s.dash[1]:g}")
        if not (s.fill or s.stroke):
            decl.append("stroke: none" if s == Style() else f"fill: {s.text}")
        if s.bold:
            decl.append("font-weight: 600")
        if s.spacing:
            decl.append(f"letter-spacing: {s.spacing:g}em")
        rules.append(f".{cls} {{ {'; '.join(decl)}; }}")
    return "\n".join(rules)


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
