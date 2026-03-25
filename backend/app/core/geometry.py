from __future__ import annotations

from typing import Iterable

from shapely.geometry import Polygon


def rectangle(x: float, y: float, w: float, h: float) -> Polygon:
    return Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])


def round_coord(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def polygon_to_points(polygon: Polygon) -> list[list[float]]:
    pts = list(polygon.exterior.coords)[:-1]
    return [[round_coord(x), round_coord(y)] for x, y in pts]


def bbox_dimensions(points: Iterable[list[float]]) -> tuple[float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)
