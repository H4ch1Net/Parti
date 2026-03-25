from __future__ import annotations

from collections import defaultdict
import math

from shapely.geometry import Polygon

from app.core.geometry import bbox_dimensions, polygon_to_points, rectangle
from app.models.schemas import RoomGeometry, Wall
from app.services.graph_placer import MIN_DIM_TABLE, RoomLayout, room_min_dims


def _snap(v: float, module_m: float) -> float:
    return round(round(v / module_m) * module_m, 3)


def _snap_dim(v: float, module_m: float) -> float:
    return round(math.ceil(v / module_m) * module_m, 3)


def _merge_axis_values(values: list[float], tol: float) -> list[float]:
    if not values:
        return []
    out: list[float] = []
    for v in sorted(values):
        if not out or abs(v - out[-1]) > tol:
            out.append(v)
        else:
            out[-1] = round((out[-1] + v) / 2.0, 3)
    return out


def _closest(value: float, merged: list[float]) -> float:
    if not merged:
        return value
    return min(merged, key=lambda x: abs(x - value))


def _room_bbox(room: RoomGeometry) -> tuple[float, float, float, float]:
    xs = [p[0] for p in room.polygon]
    ys = [p[1] for p in room.polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _resize_room(room: RoomGeometry, new_w: float, new_h: float) -> RoomGeometry:
    minx, miny, _, _ = _room_bbox(room)
    poly = rectangle(minx, miny, new_w, new_h)
    points = polygon_to_points(poly)
    rw, rd = bbox_dimensions(points)
    return room.model_copy(update={"polygon": points, "width_m": rw, "depth_m": rd, "area_sqm": float(poly.area)})


def _refine_proportions(rooms: list[RoomGeometry], total_area: float, module_m: float) -> list[RoomGeometry]:
    by_zone: dict[str, list[RoomGeometry]] = defaultdict(list)
    for r in rooms:
        by_zone[r.zone].append(r)

    bedrooms = [r for r in rooms if r.type == "bedroom"]
    master_id = max(bedrooms, key=lambda x: x.area_sqm).id if bedrooms else None

    updated: list[RoomGeometry] = []
    for room in rooms:
        rw, rd = room.width_m, room.depth_m
        aspect = max(rw, rd) / max(min(rw, rd), 0.01)
        min_w, min_h = room_min_dims(room.type, room.area_sqm, total_area, is_master=(room.id == master_id))
        target_w, target_h = rw, rd

        if aspect > 2.5:
            if rw > rd:
                target_h = min(rw / 2.5, rd + 0.6)
            else:
                target_w = min(rd / 2.5, rw + 0.6)

        target_w = max(target_w, min_w)
        target_h = max(target_h, min_h)

        target_w = _snap_dim(target_w, module_m)
        target_h = _snap_dim(target_h, module_m)
        updated.append(_resize_room(room, target_w, target_h))

    return updated


def _area_budget_fix(rooms: list[RoomGeometry], expected_area: float, module_m: float) -> list[RoomGeometry]:
    if expected_area <= 0:
        return rooms

    total = sum(r.area_sqm for r in rooms)
    gap = expected_area - total
    if abs(gap) <= expected_area * 0.05:
        return rooms

    candidates = [r for r in rooms if r.type in {"living", "bedroom"}]
    if not candidates:
        return rooms

    target = max(candidates, key=lambda x: x.area_sqm)
    bedrooms = [r for r in rooms if r.type == "bedroom"]
    master_id = max(bedrooms, key=lambda x: x.area_sqm).id if bedrooms else None

    delta_h = gap / max(target.width_m, 0.01)
    new_h = _snap_dim(target.depth_m + delta_h, module_m)

    min_w, min_h = room_min_dims(target.type, target.area_sqm, total, is_master=(target.id == master_id))
    new_h = max(_snap_dim(min_h, module_m), new_h)
    patched = _resize_room(target, target.width_m, new_h)

    out: list[RoomGeometry] = []
    for r in rooms:
        out.append(patched if r.id == target.id else r)
    return out


def _corridor_budget_fix(rooms: list[RoomGeometry], module_m: float) -> list[RoomGeometry]:
    total = sum(r.area_sqm for r in rooms)
    corridor = sum(r.area_sqm for r in rooms if r.type == "corridor")
    if total <= 0 or corridor / total <= 0.10:
        return rooms

    desired_total = corridor / 0.10
    add_area = max(0.0, desired_total - total)
    grow_targets = [r for r in rooms if r.type in {"living", "bedroom", "open_office", "reception"}]
    if not grow_targets:
        return rooms

    target = max(grow_targets, key=lambda x: x.area_sqm)
    add_h = add_area / max(target.width_m, 0.01)
    min_w, min_h = room_min_dims(target.type, target.area_sqm, total)
    new_h = max(_snap_dim(min_h, module_m), _snap_dim(target.depth_m + add_h, module_m))
    patched = _resize_room(target, target.width_m, new_h)

    out: list[RoomGeometry] = []
    for r in rooms:
        out.append(patched if r.id == target.id else r)
    return out


def _rebuild_walls(rooms: list[RoomGeometry], module_m: float) -> list[Wall]:
    # Build exterior flags from global extents after snapping and merged axes.
    all_x = [p[0] for r in rooms for p in r.polygon]
    all_y = [p[1] for r in rooms for p in r.polygon]
    minx, maxx = min(all_x), max(all_x)
    miny, maxy = min(all_y), max(all_y)

    walls: list[Wall] = []
    for room in rooms:
        pts = room.polygon + [room.polygon[0]]
        for i in range(len(pts) - 1):
            a = [_snap(pts[i][0], module_m), _snap(pts[i][1], module_m)]
            b = [_snap(pts[i + 1][0], module_m), _snap(pts[i + 1][1], module_m)]
            exterior = (
                (abs(a[0] - minx) < 0.05 and abs(b[0] - minx) < 0.05)
                or (abs(a[0] - maxx) < 0.05 and abs(b[0] - maxx) < 0.05)
                or (abs(a[1] - miny) < 0.05 and abs(b[1] - miny) < 0.05)
                or (abs(a[1] - maxy) < 0.05 and abs(b[1] - maxy) < 0.05)
            )
            walls.append(
                Wall(
                    id=f"wall_{room.id}_{i}",
                    room_id=room.id,
                    segment=[a, b],
                    thickness=0.1524 if exterior else 0.1143,
                    exterior=exterior,
                )
            )
    return walls


def refine_layout(layout: RoomLayout, expected_area: float) -> RoomLayout:
    module_m = layout.grid_module_mm / 1000.0

    # Snap room polygons to grid.
    snapped_rooms: list[RoomGeometry] = []
    for room in layout.rooms:
        snapped_poly = [[_snap(p[0], module_m), _snap(p[1], module_m)] for p in room.polygon]
        poly = Polygon(snapped_poly)
        points = polygon_to_points(poly)
        rw, rd = bbox_dimensions(points)
        snapped_rooms.append(
            room.model_copy(
                update={
                    "polygon": points,
                    "width_m": rw,
                    "depth_m": rd,
                    "area_sqm": float(poly.area),
                }
            )
        )

    # Merge near-parallel wall lines by consolidating coordinate axes within 50mm.
    all_x = [p[0] for r in snapped_rooms for p in r.polygon]
    all_y = [p[1] for r in snapped_rooms for p in r.polygon]
    merged_x = _merge_axis_values(all_x, 0.05)
    merged_y = _merge_axis_values(all_y, 0.05)

    merged_rooms: list[RoomGeometry] = []
    for room in snapped_rooms:
        poly = [[_closest(p[0], merged_x), _closest(p[1], merged_y)] for p in room.polygon]
        shp = Polygon(poly)
        pts = polygon_to_points(shp)
        rw, rd = bbox_dimensions(pts)
        merged_rooms.append(room.model_copy(update={"polygon": pts, "width_m": rw, "depth_m": rd, "area_sqm": float(shp.area)}))

    proportioned = _refine_proportions(merged_rooms, expected_area, module_m)
    budget_fixed = _area_budget_fix(proportioned, expected_area, module_m)
    corridor_fixed = _corridor_budget_fix(budget_fixed, module_m)
    rebuilt_walls = _rebuild_walls(corridor_fixed, module_m)

    return RoomLayout(
        rooms=corridor_fixed,
        walls=rebuilt_walls,
        circulation=layout.circulation,
        schedule=layout.schedule,
        zone_map=layout.zone_map,
        graph=layout.graph,
        tier_map=layout.tier_map,
        edge_map=layout.edge_map,
        grid_module_mm=layout.grid_module_mm,
        entry_wall=layout.entry_wall,
    )
