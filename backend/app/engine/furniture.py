"""Furniture and fixture placement.

Each room type has a short recipe. Items are anchored to walls (or centred)
and placed greedily: every candidate position is checked against the room's
clear floor, door swings, passage zones in front of openings and items that
are already placed, then scored by simple preferences (centred on a wall,
away from the door, under or clear of a window).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.geometry import Box, r3, side_of
from app.core.geometry import Segment as Seg
from app.engine.access import exterior_sides
from app.engine.layout import Layout, PlacedRoom
from app.engine.walls import EXTERIOR_WALL, INTERIOR_WALL
from app.models.schemas import Door, Fixture, Window

FACING = {"s": "n", "n": "s", "w": "e", "e": "w"}
OPPOSITE = {"s": "n", "n": "s", "w": "e", "e": "w"}
STEP = 0.05

# Items a room needs to be usable; missing ones lower the furniture score.
REQUIRED = {
    "bedroom": ["bed"],
    "studio": ["bed"],
    "living": ["sofa"],
    "kitchen": ["sink", "stove", "fridge"],
    "bathroom": ["toilet", "vanity", "bath_or_shower"],
    "ensuite": ["toilet", "vanity", "bath_or_shower"],
    "powder": ["toilet", "vanity"],
    "dining": ["dining_table"],
    "study": ["desk"],
    "private_office": ["desk"],
    "laundry": ["washer"],
    "garage": ["car"],
    "meeting_room": ["meeting_table"],
    "reception": ["reception_desk"],
    "open_office": ["desk"],
}


@dataclass
class RoomCtx:
    room: PlacedRoom
    clear: Box
    blocked: list[Box] = field(default_factory=list)
    window_zones: list[Box] = field(default_factory=list)
    window_spans: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    door_sides: set[str] = field(default_factory=set)
    items: list[tuple[Box, str, str]] = field(default_factory=list)
    door_points: list[tuple[float, float]] = field(default_factory=list)
    garage_side: str | None = None

    def length(self, side: str) -> float:
        return self.clear.w if side in "sn" else self.clear.h


def _seg(points: list[list[float]]) -> Seg:
    (x0, y0), (x1, y1) = points
    return Seg(x0, y0, x1, y1)


def _zone(room: Box, seg: Seg, depth: float) -> Box:
    side = side_of(room, seg)
    lo, hi = seg.lo - 0.05, seg.hi + 0.05
    if side == "s":
        return Box(lo, room.y, hi - lo, depth)
    if side == "n":
        return Box(lo, room.y1 - depth, hi - lo, depth)
    if side == "w":
        return Box(room.x, lo, depth, hi - lo)
    return Box(room.x1 - depth, lo, depth, hi - lo)


def _on_room(room: Box, seg: Seg) -> bool:
    if seg.horizontal:
        on_line = abs(seg.offset - room.y) < 1e-4 or abs(seg.offset - room.y1) < 1e-4
        return on_line and seg.lo >= room.x - 1e-4 and seg.hi <= room.x1 + 1e-4
    on_line = abs(seg.offset - room.x) < 1e-4 or abs(seg.offset - room.x1) < 1e-4
    return on_line and seg.lo >= room.y - 1e-4 and seg.hi <= room.y1 + 1e-4


def _ctx(p: PlacedRoom, layout: Layout, doors: list[Door], windows: list[Window]) -> RoomCtx:
    b = p.box
    ext = set(exterior_sides(p, layout))
    t = {s: (EXTERIOR_WALL if s in ext else INTERIOR_WALL) / 2 + 0.02 for s in "sewn"}
    ctx = RoomCtx(room=p, clear=b.inset(t["w"], t["s"], t["e"], t["n"]))
    for d in doors:
        if d.floor != p.room.floor or p.room.id not in (d.room_a, d.room_b):
            continue
        seg = _seg(d.segment)
        if not _on_room(b, seg):
            continue
        side = side_of(b, seg)
        ctx.door_sides.add(side)
        mx, my = seg.point((seg.lo + seg.hi) / 2)
        ctx.door_points.append((mx, my))
        if d.kind in ("door", "entry"):
            ctx.blocked.append(_zone(b, seg, d.width + 0.1) if d.room_b == p.room.id else _zone(b, seg, 0.6))
        elif d.kind == "opening":
            # Wide open-plan openings are walked through anywhere; only keep
            # a strip clear. Narrow cased openings need a real passage.
            ctx.blocked.append(_zone(b, seg, 0.35 if d.width >= 1.6 else 0.9))
        elif d.kind == "garage":
            ctx.garage_side = side
            ctx.blocked.append(_zone(b, seg, 0.4))
    for w in windows:
        if w.room_id != p.room.id:
            continue
        seg = _seg(w.segment)
        side = side_of(b, seg)
        ctx.window_spans.setdefault(side, []).append((seg.lo, seg.hi))
        ctx.window_zones.append(_zone(b, seg, 0.7))
    return ctx


def _rect(ctx: RoomCtx, side: str, t: float, w: float, d: float) -> Box:
    c = ctx.clear
    if side == "s":
        return Box(c.x + t, c.y, w, d)
    if side == "n":
        return Box(c.x + t, c.y + c.h - d, w, d)
    if side == "w":
        return Box(c.x, c.y + t, d, w)
    return Box(c.x + c.w - d, c.y + t, d, w)


def _front(box: Box, side: str, depth: float) -> Box:
    if depth <= 0:
        return Box(box.x, box.y, 0, 0)
    if side == "s":
        return Box(box.x, box.y + box.h, box.w, depth)
    if side == "n":
        return Box(box.x, box.y - depth, box.w, depth)
    if side == "w":
        return Box(box.x + box.w, box.y, depth, box.h)
    return Box(box.x - depth, box.y, depth, box.h)


def _free(ctx: RoomCtx, box: Box, tall: bool = False, ignore: tuple[Box, ...] = ()) -> bool:
    if not ctx.clear.contains(box):
        return False
    if any(box.intersects(z) for z in ctx.blocked):
        return False
    if tall and any(box.intersects(z) for z in ctx.window_zones):
        return False
    return not any(box.intersects(it) for it, _, _ in ctx.items if it not in ignore)


def _window_overlap(ctx: RoomCtx, side: str, box: Box) -> float:
    lo, hi = (box.x, box.x + box.w) if side in "sn" else (box.y, box.y + box.h)
    return sum(max(0.0, min(hi, b) - max(lo, a)) for a, b in ctx.window_spans.get(side, []))


def _add(ctx: RoomCtx, box: Box, kind: str, facing: str) -> Box:
    ctx.items.append((box, kind, facing))
    return box


def place_on_wall(
    ctx: RoomCtx,
    kind: str,
    w: float,
    d: float,
    sides: list[str] | None = None,
    clear: float = 0.6,
    align: str = "center",
    window: str = "neutral",  # "prefer" | "avoid" | "neutral"
    tall: bool = False,
    far_from_door: bool = False,
    target: tuple[float, float] | None = None,
) -> tuple[Box, str] | None:
    sides = sides or ["s", "e", "n", "w"]
    best = None
    for rank, side in enumerate(sides):
        length = ctx.length(side)
        if w > length + 1e-6:
            continue
        steps = int((length - w) / STEP + 1e-6)
        ts = {round(i * STEP, 3) for i in range(steps + 1)} | {round(length - w, 3)}
        for t in sorted(ts):
            box = _rect(ctx, side, t, w, d)
            if not _free(ctx, box, tall):
                continue
            fr = _front(box, side, clear)
            if clear > 0 and not (ctx.clear.contains(fr) and not any(fr.intersects(it) for it, _, _ in ctx.items)):
                continue
            score = rank * 1.5
            if align == "center":
                score += abs(t + w / 2 - length / 2)
            elif align == "corner":
                score += min(t, length - w - t)
            overlap = _window_overlap(ctx, side, box)
            if window == "prefer":
                score -= 2.0 * min(1.0, overlap / max(w, 0.1))
            elif window == "avoid" and overlap > 0:
                score += 3.0
            if far_from_door and ctx.door_points:
                score -= 0.3 * min(abs(box.cx - x) + abs(box.cy - y) for x, y in ctx.door_points)
            if target is not None:
                score += abs(box.cx - target[0]) + abs(box.cy - target[1])
            if best is None or score < best[0]:
                best = (score, box, side)
    if best is None:
        return None
    _, box, side = best
    _add(ctx, box, kind, FACING[side])
    return box, side


def place_centered(ctx: RoomCtx, kind: str, w: float, d: float, pad: float = 0.0, facing: str = "n") -> Box | None:
    """Place a free-standing item as close to the room centre as possible.

    ``pad`` is extra space kept free around the item (chairs, circulation).
    """
    c = ctx.clear
    for rot in (False, True):
        iw, id_ = (d, w) if rot else (w, d)
        if (iw > id_) != (c.w > c.h) and not rot:
            iw, id_ = id_, iw
        best = None
        span_x = c.w - iw - 2 * pad
        span_y = c.h - id_ - 2 * pad
        if span_x < -1e-6 or span_y < -1e-6:
            continue
        for i in range(-12, 13):
            for j in range(-12, 13):
                x = c.x + pad + span_x / 2 + i * STEP * 2
                y = c.y + pad + span_y / 2 + j * STEP * 2
                outer = Box(x - pad, y - pad, iw + 2 * pad, id_ + 2 * pad)
                if not _free(ctx, outer):
                    continue
                dist = abs(i) + abs(j)
                if best is None or dist < best[0]:
                    best = (dist, Box(x, y, iw, id_), outer)
        if best is not None:
            _, box, outer = best
            ctx.items.append((outer, kind + "_zone", facing))
            _add(ctx, box, kind, "e" if box.w < box.h else "n")
            return box
    return None


def _sides_by(ctx: RoomCtx, avoid_door: bool = True, avoid_window: bool = False) -> list[str]:
    def key(s: str) -> tuple:
        return (
            avoid_door and s in ctx.door_sides,
            avoid_window and bool(ctx.window_spans.get(s)),
            -ctx.length(s),
        )

    return sorted(["s", "e", "n", "w"], key=key)


# ------------------------------------------------------------- recipes ----


def _bedroom(ctx: RoomCtx, studio: bool = False) -> None:
    area = ctx.room.box.area
    primary = ctx.room.room.primary
    if studio:
        sizes = [(1.4, 2.0), (1.2, 2.0), (0.9, 2.0)]
    elif primary and area >= 15:
        sizes = [(1.6, 2.0), (1.4, 2.0)]
    elif area < 9.5:
        sizes = [(0.9, 2.0)]
    else:
        sizes = [(1.4, 2.0), (1.2, 2.0), (0.9, 2.0)]
    sides = _sides_by(ctx, avoid_window=True)
    bed = None
    for clear in (0.7, 0.55):
        for w, d in sizes:
            bed = place_on_wall(ctx, "bed", w, d, sides, clear=clear, window="avoid", far_from_door=True)
            if bed:
                break
        if bed:
            break
    if bed:
        box, side = bed
        if box.w >= 1.2 or box.h >= 1.2:
            for offset in (-1, 1):
                if side in "sn":
                    ns = Box(box.x - 0.47 if offset < 0 else box.x + box.w + 0.02, box.y if side == "s" else box.y + box.h - 0.4, 0.45, 0.4)
                else:
                    ns = Box(box.x if side == "w" else box.x + box.w - 0.4, box.y - 0.47 if offset < 0 else box.y + box.h + 0.02, 0.4, 0.45)
                if _free(ctx, ns):
                    _add(ctx, ns, "nightstand", FACING[side])
    wardrobe_sides = [s for s in _sides_by(ctx) if not bed or s != bed[1]] + ([bed[1]] if bed else [])
    for ww in (2.0, 1.6, 1.2) if area >= 14 else (1.6, 1.2, 1.0):
        if place_on_wall(ctx, "wardrobe", ww, 0.6, wardrobe_sides, clear=0.7, align="corner", tall=True):
            break
    if studio:
        _living(ctx, compact=True)
    elif area >= 12.5 and not primary:
        place_on_wall(ctx, "desk", 1.1, 0.55, _sides_by(ctx), clear=0.7, window="prefer")


def _living(ctx: RoomCtx, compact: bool = False) -> None:
    sides = _sides_by(ctx, avoid_window=True)
    sofa = None
    for w in (1.8, 1.6) if compact else (2.2, 2.0, 1.8):
        sofa = place_on_wall(ctx, "sofa", w, 0.9, sides, clear=1.5, window="avoid")
        if sofa:
            break
    if not sofa:
        return
    box, side = sofa
    tw, td = (1.0, 0.55) if not compact else (0.8, 0.5)
    gap = 0.45
    if side in "sn":
        y = box.y + box.h + gap if side == "s" else box.y - gap - td
        table = Box(box.cx - tw / 2, y, tw, td)
    else:
        x = box.x + box.w + gap if side == "w" else box.x - gap - td
        table = Box(x, box.cy - tw / 2, td, tw)
    if _free(ctx, table):
        _add(ctx, table, "coffee_table", FACING[side])
    opp = OPPOSITE[side]
    place_on_wall(ctx, "tv_unit", 1.6 if not compact else 1.2, 0.45, [opp], clear=0.0, target=(box.cx, box.cy))
    if not compact and ctx.room.box.area >= 22:
        side_walls = [s for s in ("w", "e") if side in "sn"] or ["s", "n"]
        place_on_wall(ctx, "armchair", 0.85, 0.85, side_walls, clear=0.5, target=(box.cx, box.cy))


def _dining(ctx: RoomCtx, seats: int | None = None) -> Box | None:
    area = ctx.room.box.area
    if seats is None:
        seats = 8 if area >= 16 else 6 if area >= 10 else 4
    for n in (seats, 6, 4):
        if n > seats:
            continue
        w, d = {8: (2.2, 1.0), 6: (1.8, 0.9), 4: (1.2, 0.8)}[n]
        box = place_centered(ctx, f"dining_table_{n}", w, d, pad=0.6)
        if box:
            return box
    return None


def _kitchen(ctx: RoomCtx, island: bool) -> None:
    depth = 0.6

    def runs(side: str) -> list[tuple[float, float]]:
        length = ctx.length(side)
        free = []
        start = None
        steps = int(length / STEP + 1e-6)
        for i in range(steps + 1):
            t = i * STEP
            box = _rect(ctx, side, min(t, length - STEP), STEP, depth)
            ok = _free(ctx, box)
            if ok and start is None:
                start = t
            if (not ok or i == steps) and start is not None:
                end = t if not ok else length
                if end - start >= 0.6:
                    free.append((start, end))
                start = None
        return free

    options = []
    for side in "senw":
        for lo, hi in runs(side):
            score = (hi - lo) + (1.0 if ctx.window_spans.get(side) else 0.0)
            options.append((score, side, lo, hi))
    if not options:
        return
    options.sort(reverse=True)
    _, side, lo, hi = options[0]
    length = min(hi - lo, 4.5)
    # Keep the run centred on any window so the sink can sit under it.
    if ctx.window_spans.get(side):
        wlo, whi = ctx.window_spans[side][0]
        base = ctx.clear.x if side in "sn" else ctx.clear.y
        wc = (wlo + whi) / 2 - base
        lo = min(max(lo, wc - length / 2), hi - length)
    run = (lo, lo + length)
    facing = FACING[side]

    leg = None
    if length < 2.6:
        # L-shaped kitchen: continue the counter on a neighbouring wall.
        for other in ("w", "e") if side in "sn" else ("s", "n"):
            for olo, ohi in runs(other):
                if ohi - olo >= 1.2:
                    leg = (other, olo, min(ohi, olo + 2.4))
                    break
            if leg:
                break

    items: list[tuple[str, float, float, str]] = []  # kind, t, width, side
    t0, t1 = run
    fridge_at_start = True
    if ctx.window_spans.get(side):
        base = ctx.clear.x if side in "sn" else ctx.clear.y
        wc = (ctx.window_spans[side][0][0] + ctx.window_spans[side][0][1]) / 2 - base
        fridge_at_start = abs(wc - t0) > abs(wc - t1)
    if length >= 2.4:
        if fridge_at_start:
            items.append(("fridge", t0, 0.75, side))
            t0 += 0.75
        else:
            items.append(("fridge", t1 - 0.75, 0.75, side))
            t1 -= 0.75
    elif leg:
        o_side, olo, ohi = leg
        items.append(("fridge", ohi - 0.75, 0.75, o_side))
        leg = (o_side, olo, ohi - 0.75)
    span = t1 - t0
    if span >= 2.0:
        sink_t = t0 + span * 0.62 - 0.4 if fridge_at_start else t0 + span * 0.38 - 0.4
        if ctx.window_spans.get(side):
            base = ctx.clear.x if side in "sn" else ctx.clear.y
            wc = (ctx.window_spans[side][0][0] + ctx.window_spans[side][0][1]) / 2 - base
            sink_t = min(max(wc - 0.4, t0 + 0.1), t1 - 0.9)
        stove_t = t0 + 0.2 if (sink_t - t0) > (t1 - sink_t - 0.8) else t1 - 0.8
        if abs(stove_t - sink_t) < 1.0:
            stove_t = t0 + 0.15 if sink_t > (t0 + t1) / 2 else t1 - 0.75
        items.append(("sink", sink_t, 0.8, side))
        if abs(stove_t - sink_t) >= 0.85:
            items.append(("stove", stove_t, 0.6, side))
        elif leg:
            items.append(("stove", leg[1] + 0.7, 0.6, leg[0]))
    elif span >= 0.8:
        items.append(("sink", t0 + 0.05, 0.8, side))
        if leg and leg[2] - leg[1] >= 1.4:
            items.append(("stove", leg[1] + 0.7, 0.6, leg[0]))

    counter_box = _rect(ctx, side, run[0], run[1] - run[0], depth)
    leg_box = None
    if leg:
        o_side, olo, ohi = leg
        # Start the leg clear of the main counter in the corner.
        leg_box = _rect(ctx, o_side, olo, ohi - olo, depth)
        if leg_box.intersects(counter_box):
            x0, y0, x1, y1 = leg_box.x, leg_box.y, leg_box.x + leg_box.w, leg_box.y + leg_box.h
            if side == "s":
                y0 = max(y0, counter_box.y + counter_box.h)
            elif side == "n":
                y1 = min(y1, counter_box.y)
            elif side == "w":
                x0 = max(x0, counter_box.x + counter_box.w)
            else:
                x1 = min(x1, counter_box.x)
            leg_box = Box(x0, y0, x1 - x0, y1 - y0)
    _add(ctx, counter_box, "counter", facing)
    if leg_box and leg_box.w > 0.3 and leg_box.h > 0.3:
        _add(ctx, leg_box, "counter", FACING[leg[0]])
    for kind, t, w, s in items:
        box = _rect(ctx, s, t, w, depth if kind != "fridge" else 0.7)
        if kind == "fridge" and any(box.intersects(z) for z in ctx.window_zones):
            continue
        ctx.items.append((box, kind, FACING[s]))
    # Anything the counter run could not hold goes on another free wall.
    have = {k for _, k, _ in ctx.items}
    for kind, w, d, tall in (("sink", 0.8, 0.6, False), ("stove", 0.6, 0.6, False), ("fridge", 0.75, 0.7, True)):
        if kind not in have:
            place_on_wall(ctx, kind, w, d, None, clear=0.9, align="corner", tall=tall)
    if island:
        c = ctx.clear
        if min(c.w, c.h) >= 3.7:
            place_centered(ctx, "island", 1.8, 0.9, pad=1.0)


def _bath(ctx: RoomCtx, ensuite: bool, powder: bool) -> None:
    if not powder:
        placed = None
        if ctx.room.box.area >= 4.2 and not ensuite:
            short_sides = sorted("senw", key=lambda s: (s in ctx.door_sides, ctx.length(s)))
            placed = place_on_wall(ctx, "bathtub", 1.7, 0.75, short_sides, clear=0.0, align="corner", far_from_door=True)
        if not placed:
            for size in (0.9, 0.8):
                placed = place_on_wall(ctx, "shower", size, size, _sides_by(ctx), clear=0.0, align="corner", far_from_door=True)
                if placed:
                    break
    toilet = place_on_wall(ctx, "toilet", 0.45, 0.7, _sides_by(ctx), clear=0.55, align="corner")
    if not toilet:
        place_on_wall(ctx, "toilet", 0.45, 0.65, None, clear=0.45, align="corner")
    vanity_w = 0.5 if powder else (1.2 if ensuite and ctx.room.box.area >= 6 else 0.8)
    for w in (vanity_w, 0.6, 0.5):
        if place_on_wall(ctx, "vanity", w, 0.45 if w > 0.5 else 0.4, None, clear=0.5, window="neutral"):
            break


def _laundry(ctx: RoomCtx) -> None:
    first = place_on_wall(ctx, "washer", 0.6, 0.62, _sides_by(ctx), clear=0.7, align="corner")
    if first:
        box, side = first
        place_on_wall(ctx, "dryer", 0.6, 0.62, [side], clear=0.7, target=(box.cx, box.cy))
    place_on_wall(ctx, "utility_sink", 0.55, 0.5, None, clear=0.6)


def _office(ctx: RoomCtx, guests: bool) -> None:
    desk = place_on_wall(ctx, "desk", 1.4, 0.7, _sides_by(ctx), clear=0.9, window="prefer")
    if not desk:
        place_on_wall(ctx, "desk", 1.1, 0.6, None, clear=0.8)
    place_on_wall(ctx, "bookshelf", 1.0, 0.35, _sides_by(ctx), clear=0.6, align="corner", tall=True)
    if guests:
        place_on_wall(ctx, "armchair", 0.7, 0.7, _sides_by(ctx), clear=0.4)


def _open_office(ctx: RoomCtx) -> None:
    c = ctx.clear
    dw, dd = 1.4, 0.7
    pad = 0.7
    x = c.x + pad
    placed = 0
    while x + dw <= c.x + c.w - pad + 1e-6:
        y = c.y + pad
        while y + 2 * dd <= c.y + c.h - pad + 1e-6:
            if _free(ctx, Box(x, y, dw, 2 * dd)):
                _add(ctx, Box(x, y, dw, dd), "desk", "s")
                _add(ctx, Box(x, y + dd, dw, dd), "desk", "n")
                placed += 2
            y += 2 * dd + 1.2
        x += dw + 0.3
    if placed == 0:
        _office(ctx, guests=False)


def _meeting(ctx: RoomCtx) -> None:
    c = ctx.clear
    length = max(1.2, min(max(c.w, c.h) - 1.8, 4.8))
    width = max(0.9, min(min(c.w, c.h) - 1.8, 1.2))
    if not place_centered(ctx, "meeting_table", length, width, pad=0.6):
        place_centered(ctx, "meeting_table", 1.2, 0.9, pad=0.5)


def _reception(ctx: RoomCtx) -> None:
    sides = sorted("senw", key=lambda s: (s in ctx.door_sides, -ctx.length(s)))
    place_on_wall(ctx, "reception_desk", 1.8, 0.7, sides, clear=1.0)
    place_on_wall(ctx, "sofa", 1.8, 0.8, _sides_by(ctx), clear=0.8)


def _garage(ctx: RoomCtx) -> None:
    c = ctx.clear
    cars = 3 if "3-car" in ctx.room.room.name else 2 if "2-car" in ctx.room.room.name else 1
    # Cars park nose-in, perpendicular to the garage door.
    along_x = (ctx.garage_side in ("s", "n")) if ctx.garage_side else c.w < c.h
    total = cars * 1.9 + (cars - 1) * 0.6
    for i in range(cars):
        if along_x:
            x = c.x + (c.w - total) / 2 + i * 2.5
            box = Box(x, c.y + 0.3, 1.9, min(4.7, c.h - 0.6))
        else:
            y = c.y + (c.h - total) / 2 + i * 2.5
            box = Box(c.x + 0.3, y, min(4.7, c.w - 0.6), 1.9)
        if ctx.clear.contains(box):
            _add(ctx, box, "car", "s" if along_x else "w")


def _storage(ctx: RoomCtx) -> None:
    for side in _sides_by(ctx)[:2]:
        length = ctx.length(side) - 0.1
        if length >= 0.8:
            place_on_wall(ctx, "shelving", length, 0.4, [side], clear=0.6, align="corner")


def _server(ctx: RoomCtx) -> None:
    side = _sides_by(ctx)[0]
    n = max(1, min(6, int((ctx.length(side) - 0.2) / 0.65)))
    for _ in range(n):
        if not place_on_wall(ctx, "rack", 0.6, 1.0, [side], clear=0.9, align="corner"):
            break


def _entry(ctx: RoomCtx) -> None:
    place_on_wall(ctx, "closet", 1.2, 0.6, _sides_by(ctx), clear=0.7, align="corner", tall=True) or place_on_wall(
        ctx, "bench", 1.0, 0.4, None, clear=0.5
    )


def _break_room(ctx: RoomCtx) -> None:
    _kitchen(ctx, island=False)
    _dining(ctx, seats=4)


def furnish(layout: Layout, doors: list[Door], windows: list[Window]) -> tuple[list[Fixture], dict[str, list[str]]]:
    """Return fixtures and, per room, the required items that did not fit."""
    has_dining = any(p.room.type == "dining" for p in layout.rooms)
    fixtures: list[Fixture] = []
    missing: dict[str, list[str]] = {}
    for p in layout.rooms:
        ctx = _ctx(p, layout, doors, windows)
        t = p.room.type
        if ctx.clear.w <= 0.3 or ctx.clear.h <= 0.3:
            continue
        if t == "bedroom":
            _bedroom(ctx)
        elif t == "studio":
            _bedroom(ctx, studio=True)
            if not has_dining:
                _dining(ctx, seats=4)
        elif t == "living":
            _living(ctx)
            if not has_dining and p.box.area >= 22:
                _dining(ctx, seats=4)
        elif t == "dining":
            _dining(ctx)
        elif t == "kitchen":
            _kitchen(ctx, island=p.box.short >= 3.9)
            if not has_dining and p.box.area >= 11:
                _dining(ctx, seats=4)
        elif t in ("bathroom", "ensuite", "powder"):
            _bath(ctx, ensuite=t == "ensuite", powder=t == "powder")
        elif t == "laundry":
            _laundry(ctx)
        elif t in ("study", "private_office"):
            _office(ctx, guests=t == "private_office" and p.box.area >= 10)
        elif t == "open_office":
            _open_office(ctx)
        elif t == "meeting_room":
            _meeting(ctx)
        elif t == "reception":
            _reception(ctx)
        elif t == "garage":
            _garage(ctx)
        elif t == "storage":
            _storage(ctx)
        elif t == "server_room":
            _server(ctx)
        elif t == "entry":
            _entry(ctx)
        elif t == "break_room":
            _break_room(ctx)

        got = {k for _, k, _ in ctx.items}
        if got & {"bathtub", "shower"}:
            got.add("bath_or_shower")
        if any(k.startswith("dining_table") for k in got):
            got.add("dining_table")
        need = [k for k in REQUIRED.get(t, []) if k not in got]
        if need:
            missing[p.room.id] = need
        for i, (box, kind, facing) in enumerate(ctx.items):
            if kind.endswith("_zone"):
                continue
            fixtures.append(
                Fixture(
                    id=f"fx_{p.room.id}_{i}",
                    room_id=p.room.id,
                    floor=p.room.floor,
                    type=kind,
                    footprint=[
                        [r3(x), r3(y)]
                        for x, y in ((box.x, box.y), (box.x + box.w, box.y), (box.x + box.w, box.y + box.h), (box.x, box.y + box.h))
                    ],
                    facing=facing,  # type: ignore[arg-type]
                )
            )
    return fixtures, missing
