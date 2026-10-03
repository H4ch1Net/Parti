"""Sheet -> PDF (A3 landscape, standard architectural scale)."""

from __future__ import annotations

import math
from io import BytesIO

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.drawing.sheet import Arc, Circle, Ellipse, Line, Poly, Sheet, Text
from app.drawing.style import resolve

SCALES = (50, 100, 150, 200, 250, 300, 400, 500)
MARGIN = 12 * mm
TITLE_H = 22 * mm
GAP_M = 1.0


def render_pdf(sheets: list[Sheet], title_lines: list[str]) -> bytes:
    page_w, page_h = landscape(A3)
    avail_w = page_w - 2 * MARGIN
    avail_h = page_h - 2 * MARGIN - TITLE_H
    total_w = sum(s.bounds[2] - s.bounds[0] for s in sheets) + GAP_M * (len(sheets) - 1)
    total_h = max(s.bounds[3] - s.bounds[1] for s in sheets)
    scale = next((s for s in SCALES if total_w * 1000 / s * mm <= avail_w and total_h * 1000 / s * mm <= avail_h), SCALES[-1])
    k = 1000 / scale * mm  # points per metre

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    c.setTitle(title_lines[0] if title_lines else "Parti plan")
    c.setAuthor("Parti")

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

    # Title block.
    c.setStrokeColorRGB(0.11, 0.11, 0.13)
    c.setLineWidth(0.6)
    c.line(MARGIN, MARGIN + TITLE_H - 4 * mm, page_w - MARGIN, MARGIN + TITLE_H - 4 * mm)
    for i, line in enumerate(title_lines):
        c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 13 if i == 0 else 8.5)
        shade = 0.11 if i == 0 else 0.33
        c.setFillColorRGB(shade, shade, shade + 0.01)
        c.drawString(MARGIN, MARGIN + TITLE_H - 10 * mm - i * 5 * mm, line.replace("1:100", f"1:{scale}"))
    c.setFont("Helvetica", 8.5)
    c.drawRightString(page_w - MARGIN, MARGIN + TITLE_H - 10 * mm, f"Scale 1:{scale} @ A3")
    c.showPage()
    c.save()
    return buf.getvalue()


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
        c.setFont("Helvetica-Bold" if style.bold else "Helvetica", size)
        draw = {"middle": c.drawCentredString, "start": c.drawString, "end": c.drawRightString}[item.anchor]
        draw(0, 0, item.text)
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
