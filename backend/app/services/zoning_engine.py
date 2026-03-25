from __future__ import annotations

from app.models.schemas import ProgramOutput


def build_zones(program: ProgramOutput) -> dict[str, list[str]]:
    zones = {"public": [], "private": [], "service": [], "circulation": []}
    for room in program.rooms:
        zones.setdefault(room.zone, []).append(room.id)
    return zones
