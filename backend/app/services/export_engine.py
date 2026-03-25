from __future__ import annotations

from io import BytesIO
from pathlib import Path

import ezdxf
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas

from app.models.schemas import LayoutCandidate
from app.services.drafting_engine import SCALE, draft_svg


def export_svg(candidate: LayoutCandidate, out_path: Path) -> Path:
    out_path.write_text(draft_svg(candidate), encoding="utf-8")
    return out_path


def export_pdf(candidate: LayoutCandidate, out_path: Path) -> Path:
    c = canvas.Canvas(str(out_path), pagesize=landscape(A3))
    c.setLineWidth(2.0)
    c.translate(40, 40)

    for room in candidate.rooms:
        points = [(p[0] * SCALE, p[1] * SCALE) for p in room.polygon]
        path = c.beginPath()
        path.moveTo(*points[0])
        for p in points[1:]:
            path.lineTo(*p)
        path.close()
        c.drawPath(path)

        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        c.setFont("Helvetica", 9)
        c.drawCentredString(cx, cy, f"{room.name} {room.area_sqm:.1f} sqm")

    c.showPage()
    c.save()
    return out_path


def export_dxf(candidate: LayoutCandidate, out_path: Path) -> Path:
    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()
    for room in candidate.rooms:
        pts = [(p[0], p[1]) for p in room.polygon] + [(room.polygon[0][0], room.polygon[0][1])]
        msp.add_lwpolyline(pts, close=True)
        cx = sum(p[0] for p in room.polygon) / len(room.polygon)
        cy = sum(p[1] for p in room.polygon) / len(room.polygon)
        msp.add_text(room.name, dxfattribs={"height": 0.25}).set_placement((cx, cy))

    for d in candidate.openings.get("doors", []):
        msp.add_line(tuple(d["wall_segment"][0]), tuple(d["wall_segment"][1]))

    for w in candidate.openings.get("windows", []):
        msp.add_line(tuple(w["wall_segment"][0]), tuple(w["wall_segment"][1]))

    doc.saveas(str(out_path))
    return out_path


def export_png_preview(candidate: LayoutCandidate, out_path: Path) -> Path:
    width = int(max(p[0] for r in candidate.rooms for p in r.polygon) * SCALE + 120)
    height = int(max(p[1] for r in candidate.rooms for p in r.polygon) * SCALE + 120)
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    def pt(p):
        return (p[0] * SCALE + 40, p[1] * SCALE + 40)

    for room in candidate.rooms:
        draw.polygon([pt(p) for p in room.polygon], outline=(20, 20, 20), fill=(245, 248, 250))

    for d in candidate.openings.get("doors", []):
        draw.line([pt(d["wall_segment"][0]), pt(d["wall_segment"][1])], fill=(220, 38, 38), width=2)

    for w in candidate.openings.get("windows", []):
        draw.line([pt(w["wall_segment"][0]), pt(w["wall_segment"][1])], fill=(14, 165, 233), width=3)

    image.save(out_path)
    return out_path


def export_pdf_bytes(candidate: LayoutCandidate) -> bytes:
    buff = BytesIO()
    c = canvas.Canvas(buff, pagesize=landscape(A3))
    for room in candidate.rooms:
        points = [(p[0] * SCALE + 40, p[1] * SCALE + 40) for p in room.polygon]
        path = c.beginPath()
        path.moveTo(*points[0])
        for p in points[1:]:
            path.lineTo(*p)
        path.close()
        c.drawPath(path)
    c.showPage()
    c.save()
    return buff.getvalue()
