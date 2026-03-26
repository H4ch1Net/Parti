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


_ROOM_PRIORITY = {
    "corridor": 0, "entry": 1, "bathroom": 2, "ensuite": 2, "kitchen": 3,
    "bedroom": 4, "living": 5, "dining": 5, "reception": 5, "private_office": 4,
    "open_office": 5, "meeting_room": 4, "break_room": 2, "storage": 1,
    "laundry": 1, "server_room": 1, "stair": 1, "garage": 2,
}


def _resolve_overlaps(rooms: list[RoomGeometry], module_m: float) -> list[RoomGeometry]:
    """Resolve pairwise overlaps by trimming lower-priority rooms.

    Respects minimum dimensions: will not trim a room's width or height
    below its architectural minimum.
    """
    total_area = sum(r.area_sqm for r in rooms)
    for iteration in range(10):
        any_fixed = False
        for i in range(len(rooms)):
            for j in range(i + 1, len(rooms)):
                ri, rj = rooms[i], rooms[j]
                pi = Polygon(ri.polygon)
                pj = Polygon(rj.polygon)
                inter = pi.intersection(pj)
                if inter.area < 0.01:
                    continue

                pri_i = _ROOM_PRIORITY.get(ri.type, 3)
                pri_j = _ROOM_PRIORITY.get(rj.type, 3)
                if pri_i <= pri_j:
                    trim_idx, keep_idx = i, j
                else:
                    trim_idx, keep_idx = j, i

                trim_r = rooms[trim_idx]
                keep_r = rooms[keep_idx]
                t_x0, t_y0, t_x1, t_y1 = _room_bbox(trim_r)
                k_x0, k_y0, k_x1, k_y1 = _room_bbox(keep_r)

                x_overlap = min(t_x1, k_x1) - max(t_x0, k_x0)
                y_overlap = min(t_y1, k_y1) - max(t_y0, k_y0)

                # Get min dims for the room being trimmed
                min_w, min_h = room_min_dims(trim_r.type, trim_r.area_sqm, total_area)

                if x_overlap > 0 and y_overlap > 0:
                    new_x0, new_y0 = t_x0, t_y0
                    new_w, new_h = t_x1 - t_x0, t_y1 - t_y0

                    if x_overlap <= y_overlap:
                        if t_x0 < k_x0:
                            candidate_w = _snap(max(module_m, k_x0 - t_x0), module_m)
                        else:
                            new_x0 = _snap(k_x1, module_m)
                            candidate_w = _snap(max(module_m, t_x1 - k_x1), module_m)
                        # Don't trim below min width
                        new_w = max(candidate_w, _snap_dim(min_w, module_m))
                    else:
                        if t_y0 < k_y0:
                            candidate_h = _snap(max(module_m, k_y0 - t_y0), module_m)
                        else:
                            new_y0 = _snap(k_y1, module_m)
                            candidate_h = _snap(max(module_m, t_y1 - k_y1), module_m)
                        # Don't trim below min height
                        new_h = max(candidate_h, _snap_dim(min_h, module_m))

                    poly = rectangle(new_x0, new_y0, new_w, new_h)
                    points = polygon_to_points(poly)
                    rw, rd = bbox_dimensions(points)
                    rooms[trim_idx] = trim_r.model_copy(
                        update={"polygon": points, "width_m": rw, "depth_m": rd, "area_sqm": float(poly.area)}
                    )
                    any_fixed = True
        if not any_fixed:
            break
    return rooms


def _refine_proportions(rooms: list[RoomGeometry], total_area: float, module_m: float) -> list[RoomGeometry]:
    bedrooms = [r for r in rooms if r.type == "bedroom"]
    master_id = max(bedrooms, key=lambda x: x.area_sqm).id if bedrooms else None

    updated: list[RoomGeometry] = []
    for room in rooms:
        rw, rd = room.width_m, room.depth_m
        aspect = max(rw, rd) / max(min(rw, rd), 0.01)
        min_w, min_h = room_min_dims(room.type, room.area_sqm, total_area, is_master=(room.id == master_id))
        target_w, target_h = rw, rd

        if aspect > 2.5 and room.type != "corridor":
            if rw > rd:
                target_h = min(rw / 2.5, rd + 0.6)
            else:
                target_w = min(rd / 2.5, rw + 0.6)

        target_w = max(target_w, min_w)
        target_h = max(target_h, min_h)

        # Cap individual room to 34% of total area
        max_room_area = total_area * 0.34
        if target_w * target_h > max_room_area:
            if target_w >= target_h:
                target_w = max(min_w, max_room_area / max(target_h, 0.01))
            else:
                target_h = max(min_h, max_room_area / max(target_w, 0.01))

        target_w = _snap_dim(target_w, module_m)
        target_h = _snap_dim(target_h, module_m)
        updated.append(_resize_room(room, target_w, target_h))

    return _resolve_overlaps(updated, module_m)


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

    # Don't let the target room exceed 33% of expected area
    max_room_area = expected_area * 0.33
    if target.width_m * new_h > max_room_area:
        new_h = max(_snap_dim(min_h, module_m), _snap_dim(max_room_area / max(target.width_m, 0.01), module_m))

    patched = _resize_room(target, target.width_m, new_h)

    out: list[RoomGeometry] = []
    for r in rooms:
        out.append(patched if r.id == target.id else r)
    return _resolve_overlaps(out, module_m)


def _corridor_budget_fix(rooms: list[RoomGeometry], module_m: float) -> list[RoomGeometry]:
    total = sum(r.area_sqm for r in rooms)
    corridor = sum(r.area_sqm for r in rooms if r.type == "corridor")
    if total <= 0 or corridor / total <= 0.10:
        return rooms

    # Instead of growing other rooms, shrink the corridor if it's too large.
    corridor_rooms = [r for r in rooms if r.type == "corridor"]
    if not corridor_rooms:
        return rooms

    target_corr = corridor_rooms[0]
    max_corr_area = total * 0.095  # Target ~9.5% to stay under 10%
    if target_corr.area_sqm > max_corr_area:
        rw, rd = target_corr.width_m, target_corr.depth_m
        if rw >= rd:
            new_w = _snap(max(module_m, max_corr_area / max(rd, 0.01)), module_m)
            patched = _resize_room(target_corr, new_w, rd)
        else:
            new_h = _snap(max(module_m, max_corr_area / max(rw, 0.01)), module_m)
            patched = _resize_room(target_corr, rw, new_h)
        out = [patched if r.id == target_corr.id else r for r in rooms]
        return _resolve_overlaps(out, module_m)

    # Fallback: grow a living/bedroom room but cap at 33% of total
    desired_total = corridor / 0.10
    add_area = max(0.0, desired_total - total)
    grow_targets = [r for r in rooms if r.type in {"living", "bedroom", "open_office", "reception"}]
    if not grow_targets:
        return rooms

    target = max(grow_targets, key=lambda x: x.area_sqm)
    add_h = add_area / max(target.width_m, 0.01)
    min_w, min_h = room_min_dims(target.type, target.area_sqm, total)
    new_h = max(_snap_dim(min_h, module_m), _snap_dim(target.depth_m + add_h, module_m))

    # Don't let the target room exceed 33% of new total
    max_room_area = (total + add_area) * 0.33
    if target.width_m * new_h > max_room_area:
        new_h = max(_snap_dim(min_h, module_m), _snap_dim(max_room_area / max(target.width_m, 0.01), module_m))

    patched = _resize_room(target, target.width_m, new_h)
    out = [patched if r.id == target.id else r for r in rooms]
    return _resolve_overlaps(out, module_m)


def _fill_envelope_voids(rooms: list[RoomGeometry], module_m: float, expected_area: float = 0) -> list[RoomGeometry]:
    """Expand rooms toward bounding-box edges to fill voids and reach >= 95% coverage."""
    if not rooms:
        return rooms

    all_x = [p[0] for r in rooms for p in r.polygon]
    all_y = [p[1] for r in rooms for p in r.polygon]
    minx, maxx = min(all_x), max(all_x)
    miny, maxy = min(all_y), max(all_y)
    bbox_area = (maxx - minx) * (maxy - miny)
    if bbox_area <= 0:
        return rooms

    total = sum(r.area_sqm for r in rooms)
    if total / bbox_area >= 0.95:
        return rooms

    # Don't fill voids if total would exceed the budget (prevents crossing
    # thresholds that change min dimension requirements).
    max_total = expected_area * 1.05 if expected_area > 0 else float("inf")
    if total >= max_total:
        return rooms

    tol = 0.05
    for iteration in range(3):
        any_changed = False
        for idx, room in enumerate(rooms):
            x0, y0, x1, y1 = _room_bbox(room)
            rw, rh = x1 - x0, y1 - y0
            new_x0, new_y0 = x0, y0
            new_w, new_h = rw, rh

            # If room is near an envelope edge, extend it to that edge
            if abs(x0 - minx) < tol:
                new_x0 = minx
            if abs(y0 - miny) < tol:
                new_y0 = miny
            if abs(x1 - maxx) < tol:
                new_w = _snap(maxx - new_x0, module_m)
            else:
                new_w = _snap(x1 - new_x0, module_m)
            if abs(y1 - maxy) < tol:
                new_h = _snap(maxy - new_y0, module_m)
            else:
                new_h = _snap(y1 - new_y0, module_m)

            # Also extend to fill single-module gaps at edges
            if x0 - minx > tol and x0 - minx <= module_m + tol:
                # Small gap on left — check if no other room is in that gap
                gap_occupied = any(
                    _room_bbox(r)[0] < x0 - tol and _room_bbox(r)[2] > minx + tol
                    and min(_room_bbox(r)[3], y1) - max(_room_bbox(r)[1], y0) > tol
                    for ir, r in enumerate(rooms) if ir != idx
                )
                if not gap_occupied:
                    new_x0 = minx
                    new_w = _snap(x1 - minx, module_m)
                    any_changed = True

            if maxx - x1 > tol and maxx - x1 <= module_m + tol:
                gap_occupied = any(
                    _room_bbox(r)[2] > x1 + tol and _room_bbox(r)[0] < maxx - tol
                    and min(_room_bbox(r)[3], y1) - max(_room_bbox(r)[1], y0) > tol
                    for ir, r in enumerate(rooms) if ir != idx
                )
                if not gap_occupied:
                    new_w = _snap(maxx - new_x0, module_m)
                    any_changed = True

            if y0 - miny > tol and y0 - miny <= module_m + tol:
                gap_occupied = any(
                    _room_bbox(r)[1] < y0 - tol and _room_bbox(r)[3] > miny + tol
                    and min(_room_bbox(r)[2], x1) - max(_room_bbox(r)[0], x0) > tol
                    for ir, r in enumerate(rooms) if ir != idx
                )
                if not gap_occupied:
                    new_y0 = miny
                    new_h = _snap(y1 - miny, module_m)
                    any_changed = True

            if maxy - y1 > tol and maxy - y1 <= module_m + tol:
                gap_occupied = any(
                    _room_bbox(r)[3] > y1 + tol and _room_bbox(r)[1] < maxy - tol
                    and min(_room_bbox(r)[2], x1) - max(_room_bbox(r)[0], x0) > tol
                    for ir, r in enumerate(rooms) if ir != idx
                )
                if not gap_occupied:
                    new_h = _snap(maxy - new_y0, module_m)
                    any_changed = True

            if new_x0 != x0 or new_y0 != y0 or abs(new_w - rw) > 0.01 or abs(new_h - rh) > 0.01:
                poly = rectangle(new_x0, new_y0, max(module_m, new_w), max(module_m, new_h))
                points = polygon_to_points(poly)
                rw_new, rd_new = bbox_dimensions(points)
                rooms[idx] = room.model_copy(
                    update={"polygon": points, "width_m": rw_new, "depth_m": rd_new, "area_sqm": float(poly.area)}
                )

        rooms = _resolve_overlaps(rooms, module_m)
        total = sum(r.area_sqm for r in rooms)
        if total / bbox_area >= 0.95 or not any_changed:
            break

    return rooms


def _rebuild_walls(rooms: list[RoomGeometry], module_m: float) -> list[Wall]:
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

    # Fix aspect ratios that may have been broken by overlap resolution.
    # Shrink the LONGER dimension to avoid creating new overlaps.
    for idx, room in enumerate(corridor_fixed):
        if room.type == "corridor":
            continue
        rw, rd = room.width_m, room.depth_m
        shorter = min(rw, rd)
        if shorter < 0.01:
            continue
        aspect = max(rw, rd) / shorter
        if aspect > 2.5:
            min_w, min_h = room_min_dims(room.type, room.area_sqm, expected_area)
            if rw > rd:
                # Shrink width to achieve 2.4 ratio, but respect min_w
                new_w = max(_snap_dim(min_w, module_m), _snap(rd * 2.4, module_m))
                corridor_fixed[idx] = _resize_room(room, new_w, rd)
            else:
                # Shrink depth to achieve 2.4 ratio, but respect min_h
                new_h = max(_snap_dim(min_h, module_m), _snap(rw * 2.4, module_m))
                corridor_fixed[idx] = _resize_room(room, rw, new_h)
    corridor_fixed = _resolve_overlaps(corridor_fixed, module_m)

    # Final 35% domination cap: shrink any room exceeding 35% of total.
    # Use formula: max_area = 0.34/0.66 * other_rooms_total to ensure after
    # shrinking the room, it stays below 35% of the new total.
    for _cap_iter in range(3):
        final_total = sum(r.area_sqm for r in corridor_fixed)
        if final_total <= 0:
            break
        any_capped = False
        for idx, room in enumerate(corridor_fixed):
            pct = room.area_sqm / final_total
            if pct > 0.35:
                min_w, min_h = room_min_dims(room.type, room.area_sqm, expected_area)
                other_total = final_total - room.area_sqm
                max_area = (0.34 / 0.66) * other_total  # ensures result < 35% of new total
                rw, rd = room.width_m, room.depth_m
                if rw >= rd:
                    new_w = max(_snap_dim(min_w, module_m), _snap(max_area / max(rd, 0.01), module_m))
                    corridor_fixed[idx] = _resize_room(room, new_w, rd)
                else:
                    new_h = max(_snap_dim(min_h, module_m), _snap(max_area / max(rw, 0.01), module_m))
                    corridor_fixed[idx] = _resize_room(room, rw, new_h)
                any_capped = True
        if not any_capped:
            break

    # Void-filling: expand rooms toward envelope boundaries to reach 95%+ coverage.
    corridor_fixed = _fill_envelope_voids(corridor_fixed, module_m, expected_area)

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
