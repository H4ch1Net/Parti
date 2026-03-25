from __future__ import annotations

import math
from io import StringIO

import svgwrite

from app.models.schemas import LayoutCandidate

SCALE = 45.0
PADDING = 30
DIM_OFFSET = 36


def _to_svg_xy(pt: list[float]) -> tuple[float, float]:
    return (PADDING + pt[0] * SCALE, PADDING + pt[1] * SCALE)


def _key(segment: list[list[float]]) -> tuple[tuple[float, float], tuple[float, float]]:
    a = (round(segment[0][0], 3), round(segment[0][1], 3))
    b = (round(segment[1][0], 3), round(segment[1][1], 3))
    return (a, b) if a <= b else (b, a)


def _draw_dimension(dwg: svgwrite.Drawing, a: tuple[float, float], b: tuple[float, float], text: str, vertical: bool) -> None:
    tick = 8
    dwg.add(dwg.line(start=a, end=b, stroke="#374151", stroke_width=1.2))
    if vertical:
        dwg.add(dwg.line(start=(a[0] - tick / 2, a[1]), end=(a[0] + tick / 2, a[1]), stroke="#374151", stroke_width=1.2))
        dwg.add(dwg.line(start=(b[0] - tick / 2, b[1]), end=(b[0] + tick / 2, b[1]), stroke="#374151", stroke_width=1.2))
        tx = a[0] + 10
        ty = (a[1] + b[1]) / 2
    else:
        dwg.add(dwg.line(start=(a[0], a[1] - tick / 2), end=(a[0], a[1] + tick / 2), stroke="#374151", stroke_width=1.2))
        dwg.add(dwg.line(start=(b[0], b[1] - tick / 2), end=(b[0], b[1] + tick / 2), stroke="#374151", stroke_width=1.2))
        tx = (a[0] + b[0]) / 2
        ty = a[1] - 6

    dwg.add(dwg.text(text, insert=(tx, ty), text_anchor="middle", font_size="11px", fill="#1f2937"))


def draft_svg(candidate: LayoutCandidate) -> str:
    min_x = min(p[0] for r in candidate.rooms for p in r.polygon)
    min_y = min(p[1] for r in candidate.rooms for p in r.polygon)
    max_x = max(p[0] for r in candidate.rooms for p in r.polygon)
    max_y = max(p[1] for r in candidate.rooms for p in r.polygon)
    dwg = svgwrite.Drawing(size=(PADDING * 2 + max_x * SCALE + 360, PADDING * 2 + max_y * SCALE + 120))

    dwg.add(dwg.rect(insert=(0, 0), size=(dwg['width'], dwg['height']), fill="#ffffff"))

    windows_by_wall: dict[tuple[tuple[float, float], tuple[float, float]], list[dict]] = {}
    for w in candidate.openings.get("windows", []):
        windows_by_wall.setdefault(_key(w["wall_segment"]), []).append(w)

    for wall in candidate.walls:
        a = wall.segment[0]
        b = wall.segment[1]
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        seg_len = max(0.001, math.hypot(dx, dy))
        ux, uy = dx / seg_len, dy / seg_len
        nx, ny = -uy, ux
        # Draw architectural double lines; separation encodes wall thickness.
        t_m = 0.1524 if wall.exterior else 0.1143
        off = (t_m * SCALE) / 2.0

        def _line_pts(p0, p1, sign: float):
            return (
                _to_svg_xy([p0[0] + nx * off * sign / SCALE, p0[1] + ny * off * sign / SCALE]),
                _to_svg_xy([p1[0] + nx * off * sign / SCALE, p1[1] + ny * off * sign / SCALE]),
            )

        wall_windows = windows_by_wall.get(_key(wall.segment), []) if wall.exterior else []
        if wall_windows:
            # Draw exterior wall with central gap for window, then add double-line window symbol.
            win = wall_windows[0]
            gap = min(seg_len * 0.75, max(0.9, float(win["width"])))
            m1x = (a[0] + b[0]) / 2 - ux * gap / 2
            m1y = (a[1] + b[1]) / 2 - uy * gap / 2
            m2x = (a[0] + b[0]) / 2 + ux * gap / 2
            m2y = (a[1] + b[1]) / 2 + uy * gap / 2
            for sign in (-1.0, 1.0):
                l1s, l1e = _line_pts(a, [m1x, m1y], sign)
                l2s, l2e = _line_pts([m2x, m2y], b, sign)
                dwg.add(dwg.line(start=l1s, end=l1e, stroke="#111827", stroke_width=1.35, stroke_linecap="square"))
                dwg.add(dwg.line(start=l2s, end=l2e, stroke="#111827", stroke_width=1.35, stroke_linecap="square"))

            inset = min(0.11, t_m * 0.75)
            w1a = _to_svg_xy([m1x + nx * inset, m1y + ny * inset])
            w1b = _to_svg_xy([m2x + nx * inset, m2y + ny * inset])
            w2a = _to_svg_xy([m1x - nx * inset, m1y - ny * inset])
            w2b = _to_svg_xy([m2x - nx * inset, m2y - ny * inset])
            dwg.add(dwg.line(start=w1a, end=w1b, stroke="#0ea5e9", stroke_width=1.3))
            dwg.add(dwg.line(start=w2a, end=w2b, stroke="#0ea5e9", stroke_width=1.3))
        else:
            l1s, l1e = _line_pts(a, b, -1.0)
            l2s, l2e = _line_pts(a, b, 1.0)
            dwg.add(dwg.line(start=l1s, end=l1e, stroke="#111827", stroke_width=1.35, stroke_linecap="square"))
            dwg.add(dwg.line(start=l2s, end=l2e, stroke="#111827", stroke_width=1.35, stroke_linecap="square"))

    for room in candidate.rooms:
        pts = [_to_svg_xy(p) for p in room.polygon]
        dwg.add(dwg.polygon(points=pts, fill="#f8fafc", stroke="#cbd5e1", stroke_width=0.8))

        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        label = f"{room.type.title()}: {room.area_sqm:.1f} sqm"
        max_font = max(8.5, min(12.5, min(room.width_m, room.depth_m) * 3.8))
        dwg.add(dwg.text(label, insert=(cx, cy), text_anchor="middle", font_size=f"{max_font:.1f}px", fill="#0f172a"))

    for d in candidate.openings.get("doors", []):
        a0, a1 = d["wall_segment"][0], d["wall_segment"][1]
        a, b = _to_svg_xy(a0), _to_svg_xy(a1)
        h = _to_svg_xy(d["hinge"])
        leaf = _to_svg_xy(d["leaf_end"])
        seg_len = max(0.001, math.hypot(a1[0] - a0[0], a1[1] - a0[1]))
        ux = (a1[0] - a0[0]) / seg_len
        uy = (a1[1] - a0[1]) / seg_len
        closed = _to_svg_xy([d["hinge"][0] + ux * d["width"], d["hinge"][1] + uy * d["width"]])
        r = d["swing_radius"] * SCALE

        dwg.add(dwg.line(start=closed, end=h, stroke="#ef4444", stroke_width=1.3))
        dwg.add(dwg.line(start=h, end=leaf, stroke="#ef4444", stroke_width=1.4))
        dwg.add(dwg.path(d=f"M {closed[0]} {closed[1]} A {r:.2f} {r:.2f} 0 0 1 {leaf[0]} {leaf[1]}", stroke="#ef4444", fill="none", stroke_width=1.1, stroke_dasharray="3,2"))

    width_text = f"{(max_x - min_x):.2f} m"
    depth_text = f"{(max_y - min_y):.2f} m"
    bottom_y = PADDING + max_y * SCALE + DIM_OFFSET
    left_x = PADDING + min_x * SCALE - DIM_OFFSET
    _draw_dimension(
        dwg,
        (PADDING + min_x * SCALE, bottom_y),
        (PADDING + max_x * SCALE, bottom_y),
        width_text,
        vertical=False,
    )
    _draw_dimension(
        dwg,
        (left_x, PADDING + min_y * SCALE),
        (left_x, PADDING + max_y * SCALE),
        depth_text,
        vertical=True,
    )

    legend_x = PADDING + max_x * SCALE + 30
    legend_y = PADDING + 20
    dwg.add(dwg.text("Legend", insert=(legend_x, legend_y), font_size="15px", font_weight="bold"))
    dwg.add(dwg.line(start=(legend_x, legend_y + 18), end=(legend_x + 25, legend_y + 18), stroke="#111827", stroke_width=7))
    dwg.add(dwg.text("Exterior Wall", insert=(legend_x + 35, legend_y + 22), font_size="11px"))
    dwg.add(dwg.line(start=(legend_x, legend_y + 38), end=(legend_x + 25, legend_y + 38), stroke="#ef4444", stroke_width=2))
    dwg.add(dwg.text("Door + Swing", insert=(legend_x + 35, legend_y + 42), font_size="11px"))
    dwg.add(dwg.line(start=(legend_x, legend_y + 58), end=(legend_x + 25, legend_y + 58), stroke="#0ea5e9", stroke_width=1.3))
    dwg.add(dwg.line(start=(legend_x, legend_y + 62), end=(legend_x + 25, legend_y + 62), stroke="#0ea5e9", stroke_width=1.3))
    dwg.add(dwg.text("Window", insert=(legend_x + 35, legend_y + 62), font_size="11px"))

    sched_y = legend_y + 95
    dwg.add(dwg.text("Room Schedule", insert=(legend_x, sched_y), font_size="14px", font_weight="bold"))
    row_y = sched_y + 18
    for row in candidate.schedule:
        dwg.add(
            dwg.text(
                f"{row.room_name}: {row.area_sqm:.2f} sqm ({row.dimensions_m})",
                insert=(legend_x, row_y),
                font_size="10px",
            )
        )
        row_y += 14

    buf = StringIO()
    dwg.write(buf)
    return buf.getvalue()
