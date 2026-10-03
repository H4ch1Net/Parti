"""Sheet -> DXF (R2010, metres, one CAD layer per drawing layer)."""

from __future__ import annotations

from io import StringIO

import ezdxf
from ezdxf.enums import TextEntityAlignment

from app.drawing.sheet import Arc, Circle, Ellipse, Line, Poly, Sheet, Text

GAP_M = 2.0

# Drawing layer -> (CAD layer name, ACI colour).
LAYERS = {
    "zones": ("A-AREA", 8),
    "furniture": ("A-FURN", 9),
    "walls": ("A-WALL", 7),
    "openings": ("A-DOOR", 1),
    "labels": ("A-ANNO-TEXT", 7),
    "dims": ("A-ANNO-DIMS", 3),
    "annot": ("A-ANNO-SYMB", 7),
}


def render_dxf(sheets: list[Sheet]) -> bytes:
    doc = ezdxf.new(dxfversion="R2010", setup=True)
    doc.units = ezdxf.units.M
    for name, color in LAYERS.values():
        if name not in doc.layers:
            doc.layers.add(name, color=color)
    doc.layers.add("A-GLAZ", color=4)
    msp = doc.modelspace()

    offset = 0.0
    for sheet in sheets:
        minx, _miny, maxx, _maxy = sheet.bounds
        dx = offset - minx

        def P(p, dx=dx):
            return (p[0] + dx, p[1])

        for layer in sheet.layers:
            cad_layer = LAYERS[layer.name][0]
            for item in layer.items:
                lay = "A-GLAZ" if item.cls.startswith("window") else cad_layer
                _add(msp, item, P, lay)
        offset += (maxx - minx) + GAP_M

    buf = StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def _add(msp, item, P, layer: str) -> None:
    attrs = {"layer": layer}
    if isinstance(item, Poly):
        pts = [P(p) for p in item.points]
        msp.add_lwpolyline(pts, close=True, dxfattribs=attrs)
        if item.cls.startswith("wall"):
            hatch = msp.add_hatch(color=7, dxfattribs=attrs)
            hatch.paths.add_polyline_path(pts, is_closed=True)
    elif isinstance(item, Line):
        msp.add_line(P(item.a), P(item.b), dxfattribs=attrs)
    elif isinstance(item, Circle):
        msp.add_circle(P(item.center), item.r, dxfattribs=attrs)
    elif isinstance(item, Ellipse):
        major = (item.rx, 0) if item.rx >= item.ry else (0, item.ry)
        ratio = min(item.rx, item.ry) / max(item.rx, item.ry)
        msp.add_ellipse(P(item.center), major_axis=major, ratio=ratio, dxfattribs=attrs)
    elif isinstance(item, Arc):
        end = item.end if item.end > item.start else item.end + 360
        msp.add_arc(P(item.center), item.radius, item.start, end, dxfattribs=attrs)
    elif isinstance(item, Text):
        align = {
            "middle": TextEntityAlignment.BOTTOM_CENTER,
            "start": TextEntityAlignment.BOTTOM_LEFT,
            "end": TextEntityAlignment.BOTTOM_RIGHT,
        }[item.anchor]
        text = msp.add_text(item.text, height=item.size * 0.72, rotation=item.rotate, dxfattribs=attrs)
        text.set_placement(P(item.pos), align=align)
