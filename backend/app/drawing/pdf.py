"""Sheet -> PDF (A3 landscape, standard architectural scale)."""

from __future__ import annotations

import math
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.drawing.sheet import Arc, Circle, Ellipse, Line, Poly, Sheet, Text
from app.drawing.style import INK, resolve
from app.drawing.titleblock import HEIGHT, TitleInfo, title_block

FONTS = Path(__file__).parent / "fonts"
SCALES = (50, 100, 150, 200, 250, 300, 400, 500)
TRIM = 6 * mm  # outer border
FRAME = 11 * mm  # inner border; the band between carries zone markers
TB_UNIT = 12 * mm  # title block drawing unit
MARGIN = FRAME + 6 * mm
TITLE_H = HEIGHT * TB_UNIT + 6 * mm
GAP_M = 1.0


@lru_cache(maxsize=1)
def _fonts() -> tuple[str, str]:
    # Archivo ships with the app (fonts/, SIL OFL) so exports match the screen.
    try:
        pdfmetrics.registerFont(TTFont("Archivo", str(FONTS / "Archivo-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("Archivo-SemiBold", str(FONTS / "Archivo-SemiBold.ttf")))
        return "Archivo", "Archivo-SemiBold"
    except Exception:  # pragma: no cover - missing or unreadable font files
        return "Helvetica", "Helvetica-Bold"


def render_pdf(sheets: list[Sheet], info: TitleInfo) -> bytes:
    page_w, page_h = landscape(A3)
    avail_w = page_w - 2 * MARGIN
    avail_h = page_h - 2 * MARGIN - TITLE_H
    total_w = sum(s.bounds[2] - s.bounds[0] for s in sheets) + GAP_M * (len(sheets) - 1)
    total_h = max(s.bounds[3] - s.bounds[1] for s in sheets)
    scale = next((s for s in SCALES if total_w * 1000 / s * mm <= avail_w and total_h * 1000 / s * mm <= avail_h), SCALES[-1])
    k = 1000 / scale * mm  # points per metre

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    c.setTitle(f"Parti · {info.title}")
    c.setAuthor("Parti")

    _frame(c, page_w, page_h)

    origin_x = MARGIN + (avail_w - total_w * k) / 2
    origin_y = MARGIN + TITLE_H + (avail_h - total_h * k) / 2
    offset = 0.0
    for sheet in sheets:
        minx, miny, maxx, maxy = sheet.bounds
        top = origin_y + total_h * k

        def P(p, minx=minx, maxy=maxy, offset=offset, top=top):
            return origin_x + (p[0] - minx + offset) * k, top - (maxy - p[1]) * k

        for layer in sheet.layers:
            for item in layer.items:
                _draw(c, item, P, k)
        offset += (maxx - minx) + GAP_M

    # Title block along the bottom of the frame.
    def T(p):
        return FRAME + p[0] * TB_UNIT, FRAME + p[1] * TB_UNIT

    for item in title_block((page_w - 2 * FRAME) / TB_UNIT, info, f"Scale 1:{scale} at A3"):
        _draw(c, item, T, TB_UNIT)
    c.showPage()
    c.save()
    return buf.getvalue()


def _frame(c, page_w: float, page_h: float) -> None:
    """Drawing-sheet border: trim line, frame, and lettered/numbered zones."""
    regular, _ = _fonts()
    _color(c, INK, False)
    _color(c, INK, True)
    c.setDash([])
    c.setLineWidth(0.3)
    c.rect(TRIM, TRIM, page_w - 2 * TRIM, page_h - 2 * TRIM)
    c.setLineWidth(1.0)
    c.rect(FRAME, FRAME, page_w - 2 * FRAME, page_h - 2 * FRAME)
    c.setLineWidth(0.3)
    c.setFont(regular, 6.5)
    mid = (TRIM + FRAME) / 2
    cols, rows = 8, 6
    for i in range(cols):
        x0 = FRAME + (page_w - 2 * FRAME) * i / cols
        x1 = FRAME + (page_w - 2 * FRAME) * (i + 1) / cols
        if i:
            c.line(x0, TRIM, x0, FRAME)
            c.line(x0, page_h - FRAME, x0, page_h - TRIM)
        for y in (mid - 2.2, page_h - mid - 2.2):
            c.drawCentredString((x0 + x1) / 2, y, str(i + 1))
    for j in range(rows):
        y0 = FRAME + (page_h - 2 * FRAME) * j / rows
        y1 = FRAME + (page_h - 2 * FRAME) * (j + 1) / rows
        if j:
            c.line(TRIM, y0, FRAME, y0)
            c.line(page_w - FRAME, y0, page_w - TRIM, y0)
        letter = "ABCDEF"[rows - 1 - j]
        for x in (mid, page_w - mid):
            c.drawCentredString(x, (y0 + y1) / 2 - 2.2, letter)


def _color(c, hex_color: str, fill: bool) -> None:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    (c.setFillColorRGB if fill else c.setStrokeColorRGB)(r, g, b)


def _apply(c, style, k: float) -> tuple[bool, bool]:
    fill = style.fill is not None
    stroke = style.stroke is not None and style.width > 0
    if fill:
        _color(c, style.fill, True)
    if stroke:
        _color(c, style.stroke, False)
        c.setLineWidth(max(0.15, style.width * k))
        if style.dash:
            c.setDash([d * k for d in style.dash])
        else:
            c.setDash([])
    return fill, stroke


def _draw(c, item, P, k: float) -> None:
    style = resolve(item.cls)
    if isinstance(item, Text):
        x, y = P(item.pos)
        _color(c, style.text, True)
        size = item.size * k
        c.saveState()
        c.translate(x, y)
        if item.rotate:
            c.rotate(item.rotate)
        regular, bold = _fonts()
        c.setFont(bold if style.bold else regular, size)
        draw = {"middle": c.drawCentredString, "start": c.drawString, "end": c.drawRightString}[item.anchor]
        draw(0, 0, item.text, charSpace=style.spacing * size)
        c.restoreState()
        return
    fill, stroke = _apply(c, style, k)
    if not fill and not stroke:
        return
    if isinstance(item, Poly):
        path = c.beginPath()
        pts = [P(p) for p in item.points]
        path.moveTo(*pts[0])
        for p in pts[1:]:
            path.lineTo(*p)
        path.close()
        c.drawPath(path, fill=int(fill), stroke=int(stroke))
    elif isinstance(item, Line):
        (x0, y0), (x1, y1) = P(item.a), P(item.b)
        c.line(x0, y0, x1, y1)
    elif isinstance(item, Circle):
        x, y = P(item.center)
        c.circle(x, y, item.r * k, fill=int(fill), stroke=int(stroke))
    elif isinstance(item, Ellipse):
        x, y = P(item.center)
        c.ellipse(x - item.rx * k, y - item.ry * k, x + item.rx * k, y + item.ry * k, fill=int(fill), stroke=int(stroke))
    elif isinstance(item, Arc):
        x, y = P(item.center)
        r = item.radius * k
        extent = (item.end - item.start) % 360 or 360
        path = c.beginPath()
        path.moveTo(x + r * math.cos(math.radians(item.start)), y + r * math.sin(math.radians(item.start)))
        path.arcTo(x - r, y - r, x + r, y + r, item.start, extent)
        c.drawPath(path, fill=0, stroke=1)
