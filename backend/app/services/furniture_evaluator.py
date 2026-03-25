from __future__ import annotations

from app.core.geometry import rectangle
from app.models.schemas import Fixture, LayoutCandidate


def _bbox(room) -> tuple[float, float, float, float]:
    xs = [p[0] for p in room.polygon]
    ys = [p[1] for p in room.polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _fits(x: float, y: float, w: float, h: float, minx: float, miny: float, maxx: float, maxy: float) -> bool:
    return x >= minx and y >= miny and x + w <= maxx and y + h <= maxy


def _push(fixtures: list[Fixture], room_id: str, fid: str, typ: str, x: float, y: float, w: float, h: float) -> None:
    poly = rectangle(x, y, w, h)
    fixtures.append(Fixture(id=fid, room_id=room_id, type=typ, footprint=[list(p) for p in list(poly.exterior.coords)[:-1]]))


def evaluate_furniture(candidate: LayoutCandidate) -> tuple[LayoutCandidate, float]:
    fixtures: list[Fixture] = []
    penalties = 0.0

    for room in candidate.rooms:
        minx, miny, maxx, maxy = _bbox(room)
        rw, rh = maxx - minx, maxy - miny
        area = room.area_sqm

        if room.type in {"bathroom", "ensuite"}:
            # Toilet + sink + shower/tub depending area.
            variants = []
            if area > 5.0:
                variants.append([
                    ("toilet", 0.38, 0.68),
                    ("sink", 0.50, 0.40),
                    ("tub", 1.70, 0.75),
                ])
                variants.append([
                    ("toilet", 0.38, 0.68),
                    ("sink", 0.50, 0.40),
                    ("shower", 0.90, 0.90),
                ])
            elif area >= 3.5:
                variants.append([
                    ("toilet", 0.38, 0.68),
                    ("sink", 0.40, 0.35),
                    ("shower", 0.80, 0.80),
                ])
            else:
                variants.append([
                    ("toilet", 0.38, 0.68),
                    ("sink", 0.40, 0.35),
                    ("shower", 0.76, 0.76),
                ])

            placed = False
            for v in variants:
                local = []
                x = minx + 0.1
                y = miny + 0.1
                ok = True
                for name, fw, fh in v:
                    if not _fits(x, y, fw, fh, minx, miny, maxx, maxy):
                        ok = False
                        break
                    local.append((name, x, y, fw, fh))
                    x += fw + 0.18
                    if x + fw > maxx:
                        x = minx + 0.1
                        y += fh + 0.18
                if ok:
                    for i, (name, px, py, fw, fh) in enumerate(local):
                        _push(fixtures, room.id, f"fx_{room.id}_{name}_{i}", name, px, py, fw, fh)
                    placed = True
                    break
            if not placed:
                penalties += 0.25

        elif room.type == "kitchen":
            # Counter + sink + stove + fridge.
            c_depth = 0.61
            if _fits(minx + 0.05, miny + 0.05, rw - 0.1, c_depth, minx, miny, maxx, maxy):
                _push(fixtures, room.id, f"fx_{room.id}_counter_1", "counter", minx + 0.05, miny + 0.05, rw - 0.1, c_depth)
            else:
                penalties += 0.15
            if _fits(minx + 0.05, miny + 0.75, c_depth, max(1.2, rh - 0.8), minx, miny, maxx, maxy):
                _push(fixtures, room.id, f"fx_{room.id}_counter_2", "counter", minx + 0.05, miny + 0.75, c_depth, max(1.2, rh - 0.8))
            if _fits(minx + 0.9, miny + 0.1, 0.75, 0.61, minx, miny, maxx, maxy):
                _push(fixtures, room.id, f"fx_{room.id}_sink", "sink", minx + 0.9, miny + 0.1, 0.75, 0.61)
            else:
                penalties += 0.2
            if _fits(minx + 1.8, miny + 0.1, 0.76, 0.61, minx, miny, maxx, maxy):
                _push(fixtures, room.id, f"fx_{room.id}_stove", "stove", minx + 1.8, miny + 0.1, 0.76, 0.61)
            else:
                penalties += 0.2
            if _fits(maxx - 0.86, miny + 0.1, 0.76, 0.76, minx, miny, maxx, maxy):
                _push(fixtures, room.id, f"fx_{room.id}_fridge", "fridge", maxx - 0.86, miny + 0.1, 0.76, 0.76)
            else:
                penalties += 0.2

        elif room.type == "bedroom":
            # Bed and closet by area scaling.
            if area < 9:
                bed = (0.90, 1.90)
            elif area < 14:
                bed = (1.35, 1.90)
            else:
                bed = (1.50, 2.00)

            if _fits(minx + 0.1, miny + 0.1, 1.2, 0.6, minx, miny, maxx, maxy):
                _push(fixtures, room.id, f"fx_{room.id}_closet", "closet", minx + 0.1, miny + 0.1, 1.2, 0.6)
            else:
                penalties += 0.15

            bx = max(minx + 0.2, maxx - bed[0] - 0.7)
            by = max(miny + 0.7, maxy - bed[1] - 0.9)
            if _fits(bx, by, bed[0], bed[1], minx, miny, maxx, maxy):
                _push(fixtures, room.id, f"fx_{room.id}_bed", "bed", bx, by, bed[0], bed[1])
            else:
                penalties += 0.25

        elif room.type == "private_office":
            if _fits(minx + 0.2, miny + 0.2, 1.8, 0.9, minx, miny, maxx, maxy):
                _push(fixtures, room.id, f"fx_{room.id}_desk", "desk", minx + 0.2, miny + 0.2, 1.8, 0.9)
            else:
                penalties += 0.2

        elif room.type == "meeting_room":
            if _fits(minx + 0.3, miny + 0.3, max(1.8, rw - 0.8), max(1.0, rh - 0.8), minx, miny, maxx, maxy):
                _push(fixtures, room.id, f"fx_{room.id}_table", "table", minx + 0.3, miny + 0.3, max(1.8, rw - 0.8), max(1.0, rh - 0.8))
            else:
                penalties += 0.2

        elif room.type == "reception":
            if _fits(minx + 0.2, miny + 0.2, 1.8, 0.6, minx, miny, maxx, maxy):
                _push(fixtures, room.id, f"fx_{room.id}_reception_desk", "reception_desk", minx + 0.2, miny + 0.2, 1.8, 0.6)

    candidate.fixtures = fixtures
    furniture_score = max(0.0, 1.0 - penalties)
    return candidate, furniture_score
