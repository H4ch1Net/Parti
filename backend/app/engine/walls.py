"""Unique wall segments derived from the room tiling."""

from __future__ import annotations

from app.core.geometry import merge_intervals, r3
from app.engine.layout import Layout
from app.models.schemas import Wall

EXTERIOR_WALL = 0.2
INTERIOR_WALL = 0.1


def build_walls(layout: Layout) -> list[Wall]:
    walls: list[Wall] = []
    n = 0
    for level in sorted({p.room.floor for p in layout.rooms}):
        horizontal: dict[float, list[tuple[float, float]]] = {}
        vertical: dict[float, list[tuple[float, float]]] = {}
        for p in layout.floor(level):
            b = p.box
            horizontal.setdefault(r3(b.y), []).append((b.x, b.x1))
            horizontal.setdefault(b.y1, []).append((b.x, b.x1))
            vertical.setdefault(r3(b.x), []).append((b.y, b.y1))
            vertical.setdefault(b.x1, []).append((b.y, b.y1))
        for y, spans in sorted(horizontal.items()):
            exterior = abs(y) < 1e-4 or abs(y - layout.depth) < 1e-4
            for lo, hi in merge_intervals(spans):
                n += 1
                walls.append(
                    Wall(
                        id=f"wall_{n}",
                        floor=level,
                        segment=[[r3(lo), y], [r3(hi), y]],
                        thickness=EXTERIOR_WALL if exterior else INTERIOR_WALL,
                        exterior=exterior,
                    )
                )
        for x, spans in sorted(vertical.items()):
            exterior = abs(x) < 1e-4 or abs(x - layout.width) < 1e-4
            for lo, hi in merge_intervals(spans):
                n += 1
                walls.append(
                    Wall(
                        id=f"wall_{n}",
                        floor=level,
                        segment=[[x, r3(lo)], [x, r3(hi)]],
                        thickness=EXTERIOR_WALL if exterior else INTERIOR_WALL,
                        exterior=exterior,
                    )
                )
    return walls
