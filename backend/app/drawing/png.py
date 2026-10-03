"""Sheet -> PNG preview (supersampled for smooth lines)."""

from __future__ import annotations

import math
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.drawing.sheet import Arc, Circle, Ellipse, Line, Poly, Sheet, Text
from app.drawing.style import resolve, rgb
from app.drawing.titleblock import HEIGHT, MIN_WIDTH, TitleInfo, title_block

FONTS = Path(__file__).parent / "fonts"
TARGET_WIDTH = 2400
SUPERSAMPLE = 2
GAP_M = 1.0
TITLE_M = 0.3 + HEIGHT + 0.4


@lru_cache(maxsize=64)
def _font(size: int, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Archivo ships with the app (fonts/, SIL OFL) so exports match the screen.
    for path in (
        FONTS / ("Archivo-SemiBold.ttf" if bold else "Archivo-Regular.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow without FreeType support
        return ImageFont.load_default()


def render_png(sheets: list[Sheet], info: TitleInfo) -> bytes:
    plans_w = sum(s.bounds[2] - s.bounds[0] for s in sheets) + GAP_M * (len(sheets) - 1)
    total_w = max(plans_w, MIN_WIDTH)
    total_h = max(s.bounds[3] - s.bounds[1] for s in sheets) + TITLE_M
    k = min(110.0, TARGET_WIDTH / total_w) * SUPERSAMPLE
    img = Image.new("RGB", (math.ceil(total_w * k), math.ceil(total_h * k)), "white")
    draw = ImageDraw.Draw(img)

    offset = (total_w - plans_w) / 2
    for sheet in sheets:
        minx, _miny, maxx, maxy = sheet.bounds

        def P(p, minx=minx, maxy=maxy, offset=offset):
            return ((p[0] - minx + offset) * k, (maxy - p[1]) * k)

        for layer in sheet.layers:
            for item in layer.items:
                _draw(img, draw, item, P, k)
        offset += (maxx - minx) + GAP_M

    def T(p):
        return ((p[0] + 0.4) * k, (total_h - 0.4 - p[1]) * k)

    for item in title_block(total_w - 0.8, info, "See scale bar"):
        _draw(img, draw, item, T, k)

    out = img.resize((img.width // SUPERSAMPLE, img.height // SUPERSAMPLE), Image.LANCZOS)
    buf = BytesIO()
    out.save(buf, format="PNG", compress_level=6)
    return buf.getvalue()


def _dashed(draw, a, b, dash, color, width) -> None:
    length = math.dist(a, b)
    if length == 0:
        return
    on, off = dash
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    t = 0.0
    while t < length:
        e = min(t + on, length)
        draw.line([(a[0] + ux * t, a[1] + uy * t), (a[0] + ux * e, a[1] + uy * e)], fill=color, width=width)
        t = e + off


def _draw(img, draw, item, P, k: float) -> None:
    style = resolve(item.cls)
    width = max(1, round(style.width * k)) if style.width else 0
    stroke = rgb(style.stroke) if style.stroke and width else None
    fill = rgb(style.fill) if style.fill else None
    if isinstance(item, Text):
        font = _font(max(6, int(item.size * k)), style.bold)
        x, y = P(item.pos)
        anchor = {"middle": "ms", "start": "ls", "end": "rs"}[item.anchor]
        if not item.rotate:
            draw.text((x, y), item.text, fill=rgb(style.text), font=font, anchor=anchor)
            return
        box = draw.textbbox((0, 0), item.text, font=font, anchor="ls")
        tw, th = box[2] - box[0] + 4, box[3] - box[1] + 4
        tile = Image.new("L", (tw, th), 0)
        ImageDraw.Draw(tile).text((2 - box[0], 2 - box[1]), item.text, fill=255, font=font, anchor="ls")
        tile = tile.rotate(item.rotate, expand=True)
        color = Image.new("RGB", tile.size, rgb(style.text))
        # Baseline sits at the anchor; for 90° the glyphs extend to the left of it.
        img.paste(color, (int(x - tile.width + 2), int(y - tile.height / 2)), tile)
        return
    if isinstance(item, Poly):
        pts = [P(p) for p in item.points]
        # Outlines are drawn as lines: ImageDraw.polygon(width>1) allocates a
        # full-canvas mask per call, which is very slow on large sheets.
        if fill:
            draw.polygon(pts, fill=fill)
        if stroke:
            draw.line([*pts, pts[0]], fill=stroke, width=width)
    elif isinstance(item, Line) and stroke:
        a, b = P(item.a), P(item.b)
        if style.dash:
            _dashed(draw, a, b, (style.dash[0] * k, style.dash[1] * k), stroke, width)
        else:
            draw.line([a, b], fill=stroke, width=width)
    elif isinstance(item, Circle):
        x, y = P(item.center)
        r = item.r * k
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill, outline=stroke, width=width or 1)
    elif isinstance(item, Ellipse):
        x, y = P(item.center)
        draw.ellipse([x - item.rx * k, y - item.ry * k, x + item.rx * k, y + item.ry * k], fill=fill, outline=stroke, width=width or 1)
    elif isinstance(item, Arc) and stroke:
        x, y = P(item.center)
        r = item.radius * k
        draw.arc([x - r, y - r, x + r, y + r], -item.end, -item.start, fill=stroke, width=width)
