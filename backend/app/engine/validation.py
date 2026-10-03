"""Plan validation.

Errors make a plan unusable (unreachable rooms, rooms too narrow to furnish,
bedrooms without a window). Warnings flag weaker design choices. The report
is computed from the public :class:`Candidate` model, so any plan posted to
the API can be checked, not only ones the engine produced.
"""

from __future__ import annotations

from collections import defaultdict, deque

from app.core.geometry import Box, shared_edge
from app.engine.furniture import REQUIRED
from app.engine.rooms import SPECS, min_side
from app.engine.windows import glazing_ratio
from app.models.schemas import Candidate, Issue, Room, ValidationReport

CRITICAL_FIXTURES = {"kitchen", "bathroom", "ensuite", "powder", "bedroom", "studio"}
PUBLIC_ROOMS = {"living", "dining", "kitchen", "studio"}


def room_box(room: Room) -> Box:
    xs = [p[0] for p in room.polygon]
    ys = [p[1] for p in room.polygon]
    return Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def reachable_rooms(candidate: Candidate) -> set[str]:
    entry = next((d for d in candidate.doors if d.kind == "entry"), None)
    if entry is None:
        return set()
    graph: dict[str, set[str]] = defaultdict(set)
    for c in candidate.connections:
        graph[c.from_room].add(c.to_room)
        graph[c.to_room].add(c.from_room)
    seen = {entry.room_b}
    queue = deque([entry.room_b])
    while queue:
        cur = queue.popleft()
        for nxt in graph[cur] - seen:
            seen.add(nxt)
            queue.append(nxt)
    return seen


def fixture_kinds(candidate: Candidate) -> dict[str, set[str]]:
    kinds: dict[str, set[str]] = defaultdict(set)
    for f in candidate.fixtures:
        kinds[f.room_id].add(f.type)
        if f.type in {"bathtub", "shower"}:
            kinds[f.room_id].add("bath_or_shower")
        if f.type.startswith("dining_table"):
            kinds[f.room_id].add("dining_table")
    return kinds


def parents(candidate: Candidate) -> dict[str, str]:
    """Room each room is entered from (first connection pointing at it)."""
    out: dict[str, str] = {}
    for c in candidate.connections:
        if c.kind != "stair":
            out.setdefault(c.to_room, c.from_room)
    return out


def validate_candidate(
    candidate: Candidate,
    target_area_sqm: float | None = None,
    check_fixtures: bool = True,
) -> ValidationReport:
    issues: list[Issue] = []

    def add(severity: str, code: str, message: str, *rooms: str) -> None:
        issues.append(Issue(severity=severity, code=code, message=message, room_ids=list(rooms)))  # type: ignore[arg-type]

    by_id = {r.id: r for r in candidate.rooms}
    boxes = {r.id: room_box(r) for r in candidate.rooms}

    # Geometry: rooms tile each level of the footprint.
    for level in sorted({r.floor for r in candidate.rooms}):
        level_rooms = [r for r in candidate.rooms if r.floor == level]
        for i, a in enumerate(level_rooms):
            for b in level_rooms[i + 1 :]:
                if boxes[a.id].intersects(boxes[b.id], tol=0.01):
                    add("error", "geometry.overlap", f"{a.name} overlaps {b.name}", a.id, b.id)
        covered = sum(boxes[r.id].area for r in level_rooms)
        gross = candidate.footprint.width_m * candidate.footprint.depth_m
        if gross > 0 and covered < gross * 0.98:
            add("error", "geometry.void", f"Level {level} has {gross - covered:.1f} m² not assigned to any room")

    # Access.
    if not any(d.kind == "entry" for d in candidate.doors):
        add("error", "access.entry", "No front door: the entry room has no usable exterior wall")
    reach = reachable_rooms(candidate)
    for r in candidate.rooms:
        if r.id not in reach:
            add("error", "access.unreachable", f"{r.name} cannot be reached from the front door", r.id)

    # Dimensions.
    for r in candidate.rooms:
        b = boxes[r.id]
        need = min_side(r.type, r.primary)
        if b.short + 0.01 < need:
            add("error", "dims.min_width", f"{r.name} is {b.short:.2f} m wide; needs at least {need:.1f} m", r.id)
        limit = SPECS[r.type].max_aspect
        if b.aspect > limit + 0.01:
            add("warning", "dims.aspect", f"{r.name} is long and narrow (1:{b.aspect:.1f})", r.id)
        if r.target_area_sqm > 0 and r.type not in {"corridor", "stair"}:
            ratio = r.area_sqm / r.target_area_sqm
            if ratio < 0.75:
                add("warning", "area.cramped", f"{r.name} is {r.area_sqm:.1f} m², {100 - ratio * 100:.0f}% under its target", r.id)
            elif ratio > 1.75:
                add("warning", "area.oversized", f"{r.name} is {r.area_sqm:.1f} m², {ratio * 100 - 100:.0f}% over its target", r.id)

    total = candidate.total_area_sqm
    if target_area_sqm:
        dev = (total - target_area_sqm) / target_area_sqm
        if abs(dev) > 0.10:
            add("warning", "area.total", f"Total area {total:.1f} m² is {dev * 100:+.0f}% off the {target_area_sqm:.1f} m² target")

    corridor = sum(r.area_sqm for r in candidate.rooms if r.type == "corridor")
    if total > 0 and corridor / total > 0.15:
        add("warning", "circulation.share", f"Halls take {corridor / total:.0%} of the floor area")

    # Daylight.
    windows_by_room: dict[str, list] = defaultdict(list)
    for w in candidate.windows:
        windows_by_room[w.room_id].append(w)
    for r in candidate.rooms:
        if not SPECS[r.type].habitable:
            continue
        wins = windows_by_room[r.id]
        if not wins:
            add("error", "daylight.none", f"{r.name} has no window", r.id)
        elif glazing_ratio(r.area_sqm, wins) < 0.10:
            add("warning", "daylight.low", f"{r.name} glazing is below 10% of its floor area", r.id)

    # Privacy: where private rooms are entered from.
    entered_from = parents(candidate)
    for r in candidate.rooms:
        src = by_id.get(entered_from.get(r.id, ""))
        if src is None:
            continue
        if r.type == "bedroom" and src.type in PUBLIC_ROOMS:
            add("warning", "privacy.bedroom", f"{r.name} opens directly off the {src.name.lower()}", r.id, src.id)
        if r.type in {"bathroom", "powder"} and src.type in PUBLIC_ROOMS:
            add("warning", "privacy.bathroom", f"{r.name} opens directly off the {src.name.lower()}", r.id, src.id)
    for r in candidate.rooms:
        if r.type != "garage":
            continue
        for o in candidate.rooms:
            if o.type == "bedroom" and o.floor == r.floor and shared_edge(boxes[r.id], boxes[o.id]):
                add("warning", "privacy.garage", f"{o.name} shares a wall with the garage", o.id, r.id)

    # Fixtures.
    if check_fixtures:
        kinds = fixture_kinds(candidate)
        for r in candidate.rooms:
            missing = [k for k in REQUIRED.get(r.type, []) if k not in kinds[r.id]]
            if not missing:
                continue
            label = ", ".join(m.replace("_", " ").replace("bath or shower", "bath/shower") for m in missing)
            severity = "error" if r.type in CRITICAL_FIXTURES else "warning"
            add(severity, "fixtures.missing", f"{r.name} has no room for: {label}", r.id)

    valid = not any(i.severity == "error" for i in issues)
    issues.sort(key=lambda i: (i.severity != "error", i.code))
    return ValidationReport(valid=valid, issues=issues)
