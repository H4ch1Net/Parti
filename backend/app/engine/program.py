"""Brief -> room program.

Expands room counts into named rooms, assigns levels, decides where a hall is
needed and scales every room so the program adds up to the requested area.
"""

from __future__ import annotations

from app.engine.rooms import PRIMARY_BEDROOM_AREA, SPECS
from app.models.schemas import AdjacencyPreference, Program, ProgramRoom, StructuredBrief

HALL_SHARE = 0.08  # expected hall area as a share of a level with a hall
STAIR_AREA = 5.4  # 1.2 m wide straight run, ~4.5 m long

# Pairs of room types that should touch or connect, with a weight 0..1.
ADJACENCY: dict[frozenset[str], float] = {
    frozenset({"entry", "living"}): 1.0,
    frozenset({"entry", "corridor"}): 0.8,
    frozenset({"entry", "stair"}): 0.7,
    frozenset({"entry", "garage"}): 0.6,
    frozenset({"entry", "powder"}): 0.5,
    frozenset({"entry", "studio"}): 1.0,
    frozenset({"living", "dining"}): 1.0,
    frozenset({"dining", "kitchen"}): 1.0,
    frozenset({"living", "kitchen"}): 0.7,
    frozenset({"studio", "kitchen"}): 1.0,
    frozenset({"living", "corridor"}): 0.6,
    frozenset({"kitchen", "laundry"}): 0.5,
    frozenset({"kitchen", "storage"}): 0.4,
    frozenset({"kitchen", "garage"}): 0.4,
    frozenset({"bedroom", "corridor"}): 1.0,
    frozenset({"bathroom", "corridor"}): 1.0,
    frozenset({"bedroom", "ensuite"}): 1.0,
    frozenset({"study", "corridor"}): 0.6,
    frozenset({"study", "living"}): 0.4,
    frozenset({"laundry", "corridor"}): 0.5,
    frozenset({"reception", "corridor"}): 1.0,
    frozenset({"reception", "meeting_room"}): 0.8,
    frozenset({"reception", "open_office"}): 0.6,
    frozenset({"private_office", "corridor"}): 1.0,
    frozenset({"meeting_room", "corridor"}): 0.8,
    frozenset({"open_office", "corridor"}): 0.8,
    frozenset({"open_office", "break_room"}): 0.6,
    frozenset({"break_room", "corridor"}): 0.6,
    frozenset({"server_room", "open_office"}): 0.4,
    frozenset({"stair", "corridor"}): 1.0,
}

UPPER_FLOOR_TYPES = {"bedroom", "bathroom", "ensuite", "storage"}


def _names(room_type: str, count: int, primary_bedroom: bool) -> list[str]:
    label = SPECS[room_type].label
    if room_type == "bedroom" and primary_bedroom:
        return ["Primary bedroom"] + [f"Bedroom {i}" for i in range(2, count + 1)]
    if count == 1:
        return [label]
    if room_type in {"bathroom", "bedroom"}:
        return [label] + [f"{label} {i}" for i in range(2, count + 1)]
    return [f"{label} {i}" for i in range(1, count + 1)]


def _base_area(room: ProgramRoom, cars: int) -> float:
    if room.type == "garage":
        return 20.0 + 16.0 * (cars - 1)
    if room.type == "bedroom" and room.primary:
        return PRIMARY_BEDROOM_AREA
    return SPECS[room.type].base_area


def _assign_floors(rooms: list[ProgramRoom], stories: int, commercial: bool, base: dict[str, float]) -> None:
    if stories == 1:
        return
    upper = list(range(2, stories + 1))
    if commercial:
        movable = [r for r in rooms if r.type in {"private_office", "open_office", "server_room", "storage"}]
        for i, r in enumerate(movable):
            r.floor = upper[i % len(upper)] if i % stories else 1
    else:
        private = [r for r in rooms if r.type in UPPER_FLOOR_TYPES]
        private.sort(key=lambda r: (not r.primary, r.type != "ensuite", r.id))
        for i, r in enumerate(private):
            r.floor = upper[-1] if r.primary or r.type == "ensuite" else upper[i % len(upper)]

    def load(fl: int) -> float:
        return sum(base[r.id] for r in rooms if r.floor == fl)

    # Rebalance so every level has a similar footprint: move flexible rooms
    # from the heaviest level to the lightest while that reduces the spread.
    flexible = {"study", "laundry", "storage", "bedroom", "bathroom", "private_office", "meeting_room"}
    for _ in range(12):
        loads = {fl: load(fl) for fl in range(1, stories + 1)}
        heavy = max(loads, key=loads.get)  # type: ignore[arg-type]
        light = min(loads, key=loads.get)  # type: ignore[arg-type]
        spread = loads[heavy] - loads[light]
        best = None
        for r in rooms:
            if r.floor != heavy or r.type not in flexible or r.primary:
                continue
            new_spread = abs(spread - 2 * base[r.id])
            if new_spread < spread - 1.0 and (best is None or new_spread < best[0]):
                best = (new_spread, r)
        if best is None:
            break
        best[1].floor = light


def _needs_hall(rooms: list[ProgramRoom]) -> bool:
    leaves = [r for r in rooms if not SPECS[r.type].serves and r.type not in {"ensuite", "garage"}]
    return len(leaves) >= 2


def _scale_targets(rooms: list[ProgramRoom], base: dict[str, float], total: float) -> None:
    fixed = sum(r.target_area_sqm for r in rooms if r.type in {"corridor", "stair"})
    scalable = [r for r in rooms if r.type not in {"corridor", "stair"}]

    def area_at(f: float) -> float:
        return sum(max(r.min_area_sqm, base[r.id] * f ** SPECS[r.type].scale_exp) for r in scalable)

    budget = max(total - fixed, sum(r.min_area_sqm for r in scalable))
    lo, hi = 0.05, 20.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if area_at(mid) > budget:
            hi = mid
        else:
            lo = mid
    f = (lo + hi) / 2
    for r in scalable:
        r.target_area_sqm = round(max(r.min_area_sqm, base[r.id] * f ** SPECS[r.type].scale_exp), 2)


def build_program(brief: StructuredBrief) -> Program:
    commercial = brief.building_type == "commercial"
    bedrooms = brief.count("bedroom")
    primary = bedrooms >= 2 or (bedrooms >= 1 and brief.count("ensuite") > 0)
    cars = brief.count("garage")

    rooms: list[ProgramRoom] = []
    for req in brief.rooms:
        if req.count <= 0 or req.type in {"corridor", "stair"}:
            continue
        count = 1 if req.type == "garage" else req.count
        for i, name in enumerate(_names(req.type, count, primary)):
            spec = SPECS[req.type]
            is_primary = req.type == "bedroom" and primary and i == 0
            rooms.append(
                ProgramRoom(
                    id=f"{req.type}_{i + 1}",
                    type=req.type,
                    name=f"Garage ({cars}-car)" if req.type == "garage" and cars > 1 else name,
                    zone=spec.zone,  # type: ignore[arg-type]
                    target_area_sqm=0.0,
                    min_area_sqm=max(spec.min_area, 18.0 + 14.0 * (cars - 1)) if req.type == "garage" else spec.min_area,
                    primary=is_primary,
                )
            )

    base = {r.id: _base_area(r, max(1, cars)) for r in rooms}
    _assign_floors(rooms, brief.stories, commercial, base)

    per_floor_total = brief.target_area_sqm / brief.stories
    for fl in range(1, brief.stories + 1):
        level = [r for r in rooms if r.floor == fl]
        if brief.stories > 1:
            rooms.append(
                ProgramRoom(
                    id=f"stair_{fl}",
                    type="stair",
                    name="Stair",
                    zone="circulation",
                    floor=fl,
                    target_area_sqm=STAIR_AREA,
                    min_area_sqm=3.5,
                )
            )
        if _needs_hall(level):
            rooms.append(
                ProgramRoom(
                    id=f"corridor_{fl}",
                    type="corridor",
                    name="Hall",
                    zone="circulation",
                    floor=fl,
                    target_area_sqm=round(per_floor_total * HALL_SHARE, 2),
                    min_area_sqm=2.0,
                )
            )

    _scale_targets(rooms, base, brief.target_area_sqm)
    rooms.sort(key=lambda r: (r.floor, list(SPECS).index(r.type), r.id))

    adjacency: list[AdjacencyPreference] = []
    for i, a in enumerate(rooms):
        for b in rooms[i + 1 :]:
            if a.floor != b.floor:
                continue
            w = ADJACENCY.get(frozenset({a.type, b.type}), 0.0)
            if a.type == "bedroom" and b.type == "ensuite" or b.type == "bedroom" and a.type == "ensuite":
                w = 1.0 if (a.primary or b.primary) else 0.0
            if w > 0:
                adjacency.append(AdjacencyPreference(a=a.id, b=b.id, weight=w))

    return Program(target_area_sqm=brief.target_area_sqm, stories=brief.stories, rooms=rooms, adjacency=adjacency)
