from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompositionPlan:
    parti_type: str
    grid_module: int
    grid_origin: tuple[float, float]
    room_hierarchy: dict[str, int]
    edge_assignments: dict[str, list[str]]
    circulation_pattern: str
    circulation_geometry: list[list[float]]
    spatial_sequence: list[dict]
    composition_notes: list[str]


class ArchitecturalComposer:
    def _choose_parti(self, brief) -> str:
        area = brief.target_area_sqm
        btype = brief.building_type
        rooms = {r.type: r.count for r in brief.rooms}
        bedrooms = rooms.get("bedroom", 0)

        if btype == "commercial" and sum(rooms.values()) >= 5:
            return "central_core"
        if area < 80 and (rooms.get("studio", 0) > 0 or bedrooms <= 1):
            return "open_plan_bar"
        if area > 150 and ("courtyard" in brief.raw_prompt.lower() or "outdoor" in brief.raw_prompt.lower()):
            return "courtyard_l_shape"
        if bedrooms >= 3:
            return "linear_bar"
        return "split_zone"

    def _grid_module(self, area_sqm: float) -> int:
        if area_sqm < 100:
            return 900
        if area_sqm <= 200:
            return 1200
        return 1500

    def _tier_for(self, room_type: str, building_type: str) -> int:
        if building_type != "commercial":
            if room_type in {"living"}:
                return 1
            if room_type in {"kitchen", "bedroom"}:
                return 2
            if room_type in {"dining"}:
                return 3
            if room_type in {"bathroom", "ensuite", "storage", "laundry", "utility", "garage"}:
                return 4
            return 3 if room_type in {"entry", "corridor", "stair"} else 4
        else:
            if room_type in {"reception", "open_office"}:
                return 1
            if room_type in {"meeting_room", "private_office"}:
                return 2
            if room_type in {"break_room"}:
                return 3
            return 4

    def _circulation_pattern(self, parti_type: str) -> str:
        return {
            "linear_bar": "single_loaded_corridor",
            "split_zone": "cross_zone_transition",
            "central_core": "core_wrap",
            "courtyard_l_shape": "perimeter_loop",
            "open_plan_bar": "open_flow",
        }.get(parti_type, "cross_zone_transition")

    def _spatial_sequence(self, btype: str) -> list[dict]:
        seq = [
            {"zone": "outside", "width_m": 2.0},
            {"zone": "entry_threshold", "width_m": 1.0},
            {"zone": "compression", "width_m": 1.1, "length_m": 2.0},
            {"zone": "expansion_primary", "width_m": 3.8},
        ]
        if btype != "commercial":
            seq.append({"zone": "private_transition", "width_m": 1.2})
        return seq

    def compose(self, brief, program) -> CompositionPlan:
        parti = self._choose_parti(brief)
        grid = self._grid_module(brief.target_area_sqm)

        hierarchy = {r.id: self._tier_for(r.type, brief.building_type) for r in program.rooms}

        best: list[str] = []
        second: list[str] = []
        third: list[str] = []
        worst: list[str] = []

        for room in program.rooms:
            tier = hierarchy[room.id]
            if tier == 1:
                best.append(room.id)
            elif tier == 2:
                second.append(room.id)
            elif tier == 3:
                third.append(room.id)
            else:
                worst.append(room.id)

        circulation_pattern = self._circulation_pattern(parti)
        # Polyline in normalized space; layout generator maps it to actual footprint.
        circulation_geometry = [[0.5, 0.0], [0.5, 1.0]]
        if circulation_pattern == "core_wrap":
            circulation_geometry = [[0.35, 0.2], [0.65, 0.2], [0.65, 0.8], [0.35, 0.8], [0.35, 0.2]]
        elif circulation_pattern == "cross_zone_transition":
            circulation_geometry = [[0.5, 0.0], [0.5, 0.55], [0.7, 0.55]]
        elif circulation_pattern == "open_flow":
            circulation_geometry = [[0.25, 0.5], [0.75, 0.5]]

        notes = [
            f"Selected parti: {parti}",
            f"Grid module: {grid}mm",
            f"Circulation pattern: {circulation_pattern}",
        ]

        return CompositionPlan(
            parti_type=parti,
            grid_module=grid,
            grid_origin=(0.0, 0.0),
            room_hierarchy=hierarchy,
            edge_assignments={
                "best": best,
                "second": second,
                "third": third,
                "worst": worst,
            },
            circulation_pattern=circulation_pattern,
            circulation_geometry=circulation_geometry,
            spatial_sequence=self._spatial_sequence(brief.building_type),
            composition_notes=notes,
        )
