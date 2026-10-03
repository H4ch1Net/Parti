"""Title block for exported sheets.

Built from the same primitives as the plan so the SVG, PDF and PNG writers
draw it with their normal code paths. Coordinates are in drawing units with
the origin at the strip's bottom-left and y pointing up; each writer picks
the unit size (metres at plan scale for SVG/PNG, millimetres for the PDF).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.drawing.sheet import Line, Poly, Prim, Text

HEIGHT = 1.5
MIN_WIDTH = 12.0


@dataclass(frozen=True)
class TitleInfo:
    title: str
    detail: str
    date: str


def _rect(x: float, y: float, w: float, h: float) -> list[tuple[float, float]]:
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _mark(x: float, y: float, s: float) -> list[Prim]:
    """The Parti mark (frontend Icon.tsx ``Mark``), drawn in an s x s square."""

    def f(u: float, v: float) -> tuple[float, float]:
        return x + (u - 4.5) / 23 * s, y + s - (v - 4.5) / 23 * s

    return [
        Poly([f(4.5, 4.5), f(27.5, 4.5), f(27.5, 27.5), f(4.5, 27.5)], "tb-mark"),
        Line(f(4.5, 18.5), f(27.5, 18.5), "tb-mark-line"),
        Line(f(14, 4.5), f(14, 18.5), "tb-mark-line"),
        Line(f(20.5, 18.5), f(20.5, 27.5), "tb-mark-line"),
        Poly([f(16.4, 7), f(25, 7), f(25, 16), f(16.4, 16)], "tb-mark-room"),
    ]


def title_block(width: float, info: TitleInfo, scale: str) -> list[Prim]:
    """A strip ``width`` x HEIGHT: brand | drawing | status."""
    h = HEIGHT
    brand_w, status_w = 2.6, 3.2
    x1, x2 = brand_w, width - status_w
    items: list[Prim] = [Poly(_rect(0, 0, width, h), "tb-frame")]
    items += _mark(0.3, (h - 0.8) / 2, 0.8)
    items.append(Text((1.32, h / 2 - 0.13), "Parti", 0.38, "tb-brand", anchor="start"))
    items += [Line((x1, 0), (x1, h), "tb-rule"), Line((x2, 0), (x2, h), "tb-rule")]

    items.append(Text((x1 + 0.25, h - 0.34), "DRAWING", 0.12, "tb-label", anchor="start"))
    items.append(Text((x1 + 0.25, h - 0.8), info.title, 0.32, "tb-title", anchor="start"))
    items.append(Text((x1 + 0.25, 0.3), info.detail, 0.16, "tb-text", anchor="start"))

    items.append(Text((x2 + 0.25, h - 0.34), "STATUS", 0.12, "tb-label", anchor="start"))
    items.append(Text((x2 + 0.25, h - 0.76), "NOT FOR CONSTRUCTION", 0.17, "tb-accent", anchor="start"))
    items.append(Text((x2 + 0.25, 0.3), f"{scale} · {info.date}", 0.16, "tb-text", anchor="start"))
    return items
