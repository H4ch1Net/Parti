from __future__ import annotations

from app.models.schemas import LayoutCandidate


def refine_geometry(candidate: LayoutCandidate, snap: float = 0.1) -> LayoutCandidate:
    def s(v: float) -> float:
        return round(round(v / snap) * snap, 3)

    for room in candidate.rooms:
        room.polygon = [[s(x), s(y)] for x, y in room.polygon]
        room.area_sqm = round(room.area_sqm, 2)
        room.width_m = round(room.width_m, 2)
        room.depth_m = round(room.depth_m, 2)

    for wall in candidate.walls:
        wall.segment = [[s(wall.segment[0][0]), s(wall.segment[0][1])], [s(wall.segment[1][0]), s(wall.segment[1][1])]]
        wall.thickness = round(wall.thickness, 3)

    return candidate
