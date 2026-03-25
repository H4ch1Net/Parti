from __future__ import annotations

import math

from shapely.geometry import Polygon

from app.models.schemas import DoorGeometry, LayoutCandidate, WindowGeometry


DOOR_BY_TYPE = {
    "entry": 0.9,
    "bedroom": 0.8,
    "bathroom": 0.7,
    "ensuite": 0.65,
    "closet": 0.6,
    "kitchen": 0.8,
    "private_office": 0.9,
    "meeting_room": 0.9,
    "fire_exit": 1.0,
}

HABITABLE_TYPES = {"living", "bedroom", "kitchen", "dining", "studio", "private_office", "open_office", "meeting_room", "reception"}


def _poly(room) -> Polygon:
    return Polygon(room.polygon)


def _shared_segment(pa: Polygon, pb: Polygon) -> list[list[float]] | None:
    shared = pa.boundary.intersection(pb.boundary)
    if shared.is_empty:
        return None
    if shared.geom_type == "LineString" and shared.length > 0.65:
        a = shared.coords[0]
        b = shared.coords[-1]
        return [[round(a[0], 3), round(a[1], 3)], [round(b[0], 3), round(b[1], 3)]]
    if shared.geom_type == "MultiLineString":
        lines = [ln for ln in shared.geoms if ln.length > 0.65]
        if not lines:
            return None
        ln = max(lines, key=lambda l: l.length)
        a = ln.coords[0]
        b = ln.coords[-1]
        return [[round(a[0], 3), round(a[1], 3)], [round(b[0], 3), round(b[1], 3)]]
    return None


def _door_geom(segment: list[list[float]], width: float, into_poly: Polygon) -> tuple[list[float], list[float]]:
    (x1, y1), (x2, y2) = segment
    seg_len = max(0.001, math.hypot(x2 - x1, y2 - y1))
    ux, uy = (x2 - x1) / seg_len, (y2 - y1) / seg_len
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    hinge = [cx - ux * width * 0.5, cy - uy * width * 0.5]

    nx, ny = -uy, ux
    probe = Polygon([
        (hinge[0] + nx * 0.3, hinge[1] + ny * 0.3),
        (hinge[0] + nx * 0.35, hinge[1] + ny * 0.3),
        (hinge[0] + nx * 0.35, hinge[1] + ny * 0.35),
        (hinge[0] + nx * 0.3, hinge[1] + ny * 0.35),
    ]).centroid
    if not into_poly.buffer(0.02).contains(probe):
        nx, ny = -nx, -ny

    leaf = [hinge[0] + nx * width, hinge[1] + ny * width]
    return [round(hinge[0], 3), round(hinge[1], 3)], [round(leaf[0], 3), round(leaf[1], 3)]


def _pick_exterior_segment(candidate: LayoutCandidate, room_id: str) -> list[list[float]] | None:
    segs = [w.segment for w in candidate.walls if w.room_id == room_id and w.exterior]
    if not segs:
        return None
    return max(segs, key=lambda s: math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]))


def place_openings(candidate: LayoutCandidate) -> LayoutCandidate:
    rooms = {r.id: r for r in candidate.rooms}
    ids = list(rooms.keys())
    polys = {rid: _poly(r) for rid, r in rooms.items()}

    corridors = [r.id for r in candidate.rooms if r.type in {"corridor", "hallway"}]
    corridor = corridors[0] if corridors else None

    doors: list[DoorGeometry] = []
    door_idx = 1

    def add_door(a: str, b: str, width: float, swing_into: str) -> None:
        nonlocal door_idx
        if a not in polys or b not in polys:
            return
        seg = _shared_segment(polys[a], polys[b])
        if not seg:
            return
        hinge, leaf = _door_geom(seg, width, polys[swing_into])
        doors.append(
            DoorGeometry(
                id=f"door_{door_idx}",
                room_a=a,
                room_b=b,
                wall_segment=seg,
                hinge=hinge,
                leaf_end=leaf,
                swing_radius=width,
                width=width,
            )
        )
        door_idx += 1

    # Entry external door.
    entries = [r.id for r in candidate.rooms if r.type in {"entry", "reception", "lobby"}]
    if entries:
        rid = entries[0]
        seg = _pick_exterior_segment(candidate, rid)
        if seg:
            width = 1.2 if any(r.type in {"private_office", "open_office", "meeting_room", "reception"} for r in candidate.rooms) else 0.9
            hinge, leaf = _door_geom(seg, width, polys[rid])
            doors.append(
                DoorGeometry(
                    id="door_main_entry",
                    room_a="exterior",
                    room_b=rid,
                    wall_segment=seg,
                    hinge=hinge,
                    leaf_end=leaf,
                    swing_radius=width,
                    width=width,
                )
            )

    # Corridor connectivity for all non-open-plan rooms.
    if corridor:
        for r in candidate.rooms:
            if r.id == corridor:
                continue
            if r.type in {"living", "dining", "kitchen", "open_office"}:
                continue
            width = DOOR_BY_TYPE.get(r.type, 0.8)
            add_door(corridor, r.id, width, r.id)

    # Open-plan links.
    by_type = {r.type: r.id for r in candidate.rooms}
    if "entry" in by_type and "living" in by_type:
        add_door(by_type["entry"], by_type["living"], 0.9, by_type["living"])
    if "living" in by_type and "dining" in by_type:
        add_door(by_type["living"], by_type["dining"], 1.2, by_type["dining"])
    if "dining" in by_type and "kitchen" in by_type:
        add_door(by_type["dining"], by_type["kitchen"], 1.2, by_type["kitchen"])
    elif "living" in by_type and "kitchen" in by_type:
        add_door(by_type["living"], by_type["kitchen"], 1.2, by_type["kitchen"])

    # Windows per habitable room, size by 10% area target.
    windows: list[WindowGeometry] = []
    win_idx = 1
    for r in candidate.rooms:
        if r.type not in HABITABLE_TYPES and r.type != "bathroom":
            continue
        seg = _pick_exterior_segment(candidate, r.id)
        if not seg:
            continue
        seg_len = math.hypot(seg[1][0] - seg[0][0], seg[1][1] - seg[0][1])
        if r.type == "bathroom":
            width = min(seg_len * 0.6, 0.6)
        else:
            target_window_area = max(0.5, r.area_sqm * 0.10)
            assumed_height = 1.2
            width = min(seg_len * 0.75, max(0.9, target_window_area / assumed_height))
        windows.append(WindowGeometry(id=f"window_{win_idx}", room_id=r.id, wall_segment=seg, width=round(width, 2)))
        win_idx += 1

    candidate.openings = {
        "doors": [d.model_dump() for d in doors],
        "windows": [w.model_dump() for w in windows],
    }
    return candidate
