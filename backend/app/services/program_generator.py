from __future__ import annotations

from collections import defaultdict

from app.models.schemas import ProgramOutput, ProgramRoom, StructuredBrief

AREA_RATIOS = {
    "living": 0.22,
    "kitchen": 0.13,
    "dining": 0.1,
    "bedroom": 0.15,
    "bathroom": 0.06,
    "corridor": 0.06,
    "entry": 0.03,
    "studio": 0.45,
    "private_office": 0.11,
    "open_office": 0.2,
    "meeting_room": 0.12,
    "reception": 0.1,
    "break_room": 0.08,
    "server_room": 0.05,
    "garage": 0.12,
    "laundry": 0.04,
    "storage": 0.04,
    "stair": 0.04,
    "ensuite": 0.04,
}

MIN_AREA = {
    "studio": 14.0,
    "entry": 2.0,
    "living": 12.0,
    "dining": 7.2,
    "kitchen": 6.5,
    "bedroom": 9.0,
    "bathroom": 3.5,
    "ensuite": 3.0,
    "corridor": 3.0,
    "storage": 1.2,
    "utility": 2.0,
    "garage": 12.0,
    "laundry": 2.5,
    "reception": 8.0,
    "meeting_room": 12.0,
    "private_office": 8.1,
    "open_office": 20.0,
    "break_room": 7.2,
    "server_room": 5.0,
    "stair": 3.0,
}


def _zone_for(room_type: str, btype: str) -> str:
    if btype == "commercial":
        if room_type in {"reception", "lobby", "meeting_room", "open_office", "entry"}:
            return "public"
        if room_type in {"private_office", "server_room", "storage"}:
            return "private"
        if room_type in {"kitchen", "break_room", "bathroom", "utility"}:
            return "service"
        return "circulation" if room_type in {"corridor", "stair"} else "service"

    # residential / mixed default
    if room_type in {"living", "dining", "kitchen", "entry"}:
        return "public"
    if room_type in {"bedroom", "bathroom", "ensuite"}:
        return "private"
    if room_type in {"laundry", "storage", "garage", "utility"}:
        return "service"
    return "circulation" if room_type in {"corridor", "stair"} else "service"


def _adjacency_weight(a: str, b: str, btype: str) -> float:
    pair = {a, b}
    if btype != "commercial":
        if pair == {"entry", "living"}:
            return 1.0
        if pair == {"living", "dining"}:
            return 0.95
        if pair == {"dining", "kitchen"}:
            return 0.95
        if pair == {"kitchen", "corridor"}:
            return 0.65
        if pair == {"living", "corridor"}:
            return 0.9
        if "bedroom" in pair and "corridor" in pair:
            return 1.0
        if "bathroom" in pair and "corridor" in pair:
            return 1.0
        if "bedroom" in pair and "ensuite" in pair:
            return 1.0
        if pair == {"garage", "entry"} or pair == {"garage", "kitchen"}:
            return 0.7
        return 0.25

    if pair == {"reception", "entry"}:
        return 1.0
    if pair == {"reception", "corridor"}:
        return 0.95
    if "private_office" in pair and "corridor" in pair:
        return 1.0
    if "meeting_room" in pair and "corridor" in pair:
        return 0.9
    if "bathroom" in pair and "corridor" in pair:
        return 1.0
    if pair == {"break_room", "corridor"}:
        return 0.85
    return 0.25


def _floor_for(room_type: str, brief: StructuredBrief) -> int:
    if brief.story_count <= 1:
        return 1
    if room_type == "corridor":
        return 1
    # Residential heuristic: private upstairs, public downstairs.
    if brief.building_type != "commercial":
        if room_type in {"bedroom", "bathroom", "ensuite"}:
            return 2
        return 1
    # Commercial: distribute evenly but keep reception on ground.
    if room_type in {"entry", "reception"}:
        return 1
    return 1


def build_program(brief: StructuredBrief) -> ProgramOutput:
    rooms: list[ProgramRoom] = []
    room_types: dict[str, str] = {}
    target = brief.target_area_sqm

    counts = {r.type: r.count for r in brief.rooms}
    weighted_sum = 0.0
    for r in brief.rooms:
        weighted_sum += AREA_RATIOS.get(r.type, 0.07) * r.count
    weighted_sum = max(0.1, weighted_sum)

    for rr in brief.rooms:
        share = AREA_RATIOS.get(rr.type, 0.07)
        per_room_target = max(MIN_AREA.get(rr.type, 3.0), target * (share / weighted_sum))
        if rr.type == "entry":
            per_room_target = min(3.5, per_room_target)
        for i in range(rr.count):
            rid = f"{rr.type}_{i + 1}"
            room_types[rid] = rr.type
            rooms.append(
                ProgramRoom(
                    id=rid,
                    type=rr.type,
                    name=f"{rr.type.replace('_', ' ').title()} {i + 1}",
                    zone=_zone_for(rr.type, brief.building_type),
                    target_area_sqm=round(per_room_target, 2),
                    min_area_sqm=MIN_AREA.get(rr.type, 3.0),
                    floor=_floor_for(rr.type, brief),
                )
            )

    if brief.story_count > 1:
        existing_corridors = [r for r in rooms if r.type == "corridor"]
        existing_floors = {r.floor for r in existing_corridors}
        for fl in range(1, brief.story_count + 1):
            if fl in existing_floors:
                continue
            rid = f"corridor_{fl}"
            room_types[rid] = "corridor"
            rooms.append(
                ProgramRoom(
                    id=rid,
                    type="corridor",
                    name=f"Corridor {fl}",
                    zone="circulation",
                    target_area_sqm=max(4.0, target * 0.05),
                    min_area_sqm=3.0,
                    floor=fl,
                )
            )

    room_ids = [r.id for r in rooms]
    adjacency: dict[str, dict[str, float]] = {rid: {cid: 0.0 for cid in room_ids} for rid in room_ids}

    for a in room_ids:
        for b in room_ids:
            if a == b:
                continue
            adjacency[a][b] = _adjacency_weight(room_types[a], room_types[b], brief.building_type)

    # User-adjacency hints boost weights.
    for a_hint, b_hint in brief.explicit_adjacency:
        for a_id in room_ids:
            for b_id in room_ids:
                if a_id == b_id:
                    continue
                if room_types[a_id].startswith(a_hint) and room_types[b_id].startswith(b_hint):
                    adjacency[a_id][b_id] = max(adjacency[a_id][b_id], 1.0)
                    adjacency[b_id][a_id] = max(adjacency[b_id][a_id], 1.0)

    return ProgramOutput(target_area_sqm=target, rooms=rooms, adjacency_matrix=adjacency)
