"""Window placement on exterior walls."""

from __future__ import annotations

import math

from app.core.geometry import r3, side_segment, subtract_intervals
from app.engine.access import exterior_sides
from app.engine.layout import Layout
from app.engine.rooms import SPECS
from app.models.schemas import Door, Window

WINDOW_HEIGHT = 1.2  # assumed glazing height when checking daylight ratios
GLAZING_RATIO = 0.10  # glazed area as a share of floor area (common code minimum)
MAX_PANE = 2.4
NO_WINDOWS = {"corridor", "stair", "garage", "storage", "server_room"}
SMALL_WINDOWS = {"bathroom", "ensuite", "powder", "laundry", "entry"}


def _snap(v: float) -> float:
    return math.floor(v * 10 + 1e-6) / 10


def place_windows(layout: Layout, doors: list[Door]) -> list[Window]:
    windows: list[Window] = []
    door_spans: dict[tuple, list[tuple[float, float]]] = {}
    for d in doors:
        (x0, y0), (x1, y1) = d.segment
        horizontal = abs(y0 - y1) < 1e-6
        key = (d.floor, horizontal, round(y0 if horizontal else x0, 3))
        lo, hi = (min(x0, x1), max(x0, x1)) if horizontal else (min(y0, y1), max(y0, y1))
        door_spans.setdefault(key, []).append((lo - 0.3, hi + 0.3))

    n = 0
    for p in layout.rooms:
        rtype = p.room.type
        if rtype in NO_WINDOWS:
            continue
        sides = exterior_sides(p, layout)
        if not sides:
            continue
        segs = sorted((side_segment(p.box, s) for s in sides), key=lambda s: -s.length)
        if rtype in SMALL_WINDOWS:
            need = 0.6
            segs = segs[:1]
        else:
            area = p.box.area
            need = max(0.9, area * GLAZING_RATIO / WINDOW_HEIGHT * (1.4 if rtype in {"living", "dining", "studio"} else 1.25))
            # Corner rooms use a second facade when one wall is too short, and
            # living spaces always take light from both sides when they can.
            if len(segs) > 1 and (segs[0].length - 0.6 < need or rtype in {"living", "dining", "studio"}):
                segs = segs[:2]
            else:
                segs = segs[:1]

        total_len = sum(s.length for s in segs)
        for seg in segs:
            share = need * seg.length / total_len if len(segs) > 1 else need
            key = (p.room.floor, seg.horizontal, round(seg.offset, 3))
            free = subtract_intervals((seg.lo + 0.3, seg.hi - 0.3), door_spans.get(key, []))
            free = [f for f in free if f[1] - f[0] >= 0.6]
            if not free:
                continue
            lo, hi = max(free, key=lambda f: f[1] - f[0])
            avail = hi - lo
            width = min(share, avail)
            panes = max(1, math.ceil(width / MAX_PANE - 1e-6))
            pane_w = _snap(min(MAX_PANE, width / panes))
            if pane_w < 0.5:
                continue
            gap = (avail - pane_w * panes) / (panes + 1)
            for k in range(panes):
                a = lo + gap * (k + 1) + pane_w * k
                p0, p1 = seg.point(a), seg.point(a + pane_w)
                n += 1
                windows.append(
                    Window(
                        id=f"window_{n}",
                        room_id=p.room.id,
                        floor=p.room.floor,
                        segment=[[r3(p0[0]), r3(p0[1])], [r3(p1[0]), r3(p1[1])]],
                        width=r3(pane_w),
                    )
                )
    return windows


def glazing_ratio(room_area: float, windows: list[Window]) -> float:
    return sum(w.width for w in windows) * WINDOW_HEIGHT / max(room_area, 0.01)


def wants_daylight(room_type: str) -> bool:
    return SPECS[room_type].habitable
