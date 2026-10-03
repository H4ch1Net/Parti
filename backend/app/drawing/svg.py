"""Sheet -> SVG.

``mode="app"`` produces markup for the web client: no inline styles, both
unit systems present (toggled by CSS), and ``data-room`` hooks for hover and
selection. ``mode="export"`` produces a standalone drawing at 1:100 with an
embedded stylesheet and a title block.
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape, quoteattr

from app.drawing.sheet import Arc, Circle, Ellipse, Line, Poly, Sheet, Text
from app.drawing.style import css
from app.drawing.titleblock import HEIGHT, MIN_WIDTH, TitleInfo, title_block

FONT = "Archivo, 'Helvetica Neue', Arial, sans-serif"


def _f(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".") or "0"


class _Writer:
    def __init__(self, maxy: float, dx: float) -> None:
        self.maxy = maxy
        self.dx = dx
        self.parts: list[str] = []

    def xy(self, p: tuple[float, float]) -> tuple[float, float]:
        return p[0] + self.dx, self.maxy - p[1]

    def prim(self, item, mode: str) -> None:
        if isinstance(item, Poly):
            attrs = "".join(f" {k}={quoteattr(v)}" for k, v in item.attrs.items()) if mode == "app" else ""
            pts = [self.xy(p) for p in item.points]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            axis_rect = len(pts) == 4 and len(set(round(x, 4) for x in xs)) == 2 and len(set(round(y, 4) for y in ys)) == 2
            if axis_rect:
                x0, y0 = min(xs), min(ys)
                rx = f' rx="{_f(item.rx)}"' if item.rx else ""
                self.parts.append(
                    f'<rect class="{item.cls}" x="{_f(x0)}" y="{_f(y0)}" width="{_f(max(xs) - x0)}" height="{_f(max(ys) - y0)}"{rx}{attrs}/>'
                )
            else:
                d = " ".join(f"{_f(x)},{_f(y)}" for x, y in pts)
                self.parts.append(f'<polygon class="{item.cls}" points="{d}"{attrs}/>')
        elif isinstance(item, Line):
            (x0, y0), (x1, y1) = self.xy(item.a), self.xy(item.b)
            self.parts.append(f'<line class="{item.cls}" x1="{_f(x0)}" y1="{_f(y0)}" x2="{_f(x1)}" y2="{_f(y1)}"/>')
        elif isinstance(item, Circle):
            x, y = self.xy(item.center)
            self.parts.append(f'<circle class="{item.cls}" cx="{_f(x)}" cy="{_f(y)}" r="{_f(item.r)}"/>')
        elif isinstance(item, Ellipse):
            x, y = self.xy(item.center)
            self.parts.append(f'<ellipse class="{item.cls}" cx="{_f(x)}" cy="{_f(y)}" rx="{_f(item.rx)}" ry="{_f(item.ry)}"/>')
        elif isinstance(item, Arc):
            cx, cy = item.center
            a0, a1 = math.radians(item.start), math.radians(item.end)
            s = self.xy((cx + item.radius * math.cos(a0), cy + item.radius * math.sin(a0)))
            e = self.xy((cx + item.radius * math.cos(a1), cy + item.radius * math.sin(a1)))
            large = 1 if (item.end - item.start) % 360 > 180 else 0
            r = _f(item.radius)
            self.parts.append(f'<path class="{item.cls}" d="M{_f(s[0])},{_f(s[1])} A{r},{r} 0 {large} 0 {_f(e[0])},{_f(e[1])}"/>')
        elif isinstance(item, Text):
            variants = [(item.text, "")] if item.alt is None or mode != "app" else [(item.text, " u-m"), (item.alt, " u-i")]
            x, y = self.xy(item.pos)
            anchor = {"middle": "middle", "start": "start", "end": "end"}[item.anchor]
            rot = f' transform="rotate({_f(-item.rotate)} {_f(x)} {_f(y)})"' if item.rotate else ""
            for text, extra in variants:
                self.parts.append(
                    f'<text class="{item.cls}{extra}" x="{_f(x)}" y="{_f(y)}" font-size="{_f(item.size)}" text-anchor="{anchor}"{rot}>{escape(text)}</text>'
                )


def render_svg(sheets: list[Sheet], mode: str = "app", info: TitleInfo | None = None) -> str:
    gap = 1.0
    widths = [s.bounds[2] - s.bounds[0] for s in sheets]
    heights = [s.bounds[3] - s.bounds[1] for s in sheets]
    plans_w = sum(widths) + gap * (len(sheets) - 1)
    plan_h = max(heights)
    block = mode == "export" and info is not None
    total_w = max(plans_w, MIN_WIDTH) if block else plans_w
    total_h = plan_h + (0.3 + HEIGHT + 0.4 if block else 0.0)

    body: list[str] = []
    offset = (total_w - plans_w) / 2
    for sheet, w in zip(sheets, widths):
        minx, miny, maxx, maxy = sheet.bounds
        writer = _Writer(maxy, offset - minx)
        body.append('<g class="pt-sheet">')
        for layer in sheet.layers:
            writer.parts = []
            for item in layer.items:
                writer.prim(item, mode)
            body.append(f'<g class="pt-{layer.name}">' + "".join(writer.parts) + "</g>")
        body.append("</g>")
        offset += w + gap

    if block:
        writer = _Writer(total_h - 0.4, 0.4)
        for item in title_block(total_w - 0.8, info, "Scale 1:100 at printed size"):
            writer.prim(item, mode)
        body.append('<g class="pt-titleblock">' + "".join(writer.parts) + "</g>")

    vb = f"0 0 {_f(total_w)} {_f(total_h)}"
    if mode == "app":
        # Box of the building itself (without dimension margins), in SVG units.
        minx, _miny, _maxx, maxy = sheets[0].bounds
        pb = sheets[0].plan_box
        plan = f"{_f(pb.x - minx)} {_f(maxy - pb.y1)} {_f(pb.w)} {_f(pb.h)}"
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" class="pt-plan" viewBox="{vb}" data-plan="{plan}" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(body)}</svg>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{_f(total_w * 10)}mm" height="{_f(total_h * 10)}mm">'
        f"<style>{css(FONT)}</style>"
        f'<rect class="bg" x="0" y="0" width="{_f(total_w)}" height="{_f(total_h)}"/>' + "".join(body) + "</svg>"
    )
