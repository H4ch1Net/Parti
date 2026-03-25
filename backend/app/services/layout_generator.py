from __future__ import annotations

from app.models.schemas import LayoutCandidate, ProgramOutput, ScoreBreakdown, ValidationReport
from app.services.graph_placer import place_room_graph
from app.services.grid_refiner import refine_layout
from app.services.parti_selector import PartiDecision, ProgramBrief


def generate_layout_candidates(
    program: ProgramOutput,
    brief: ProgramBrief,
    parti: PartiDecision,
    zones: dict[str, list[str]],
    count: int = 8,
    variant_offset: int = 0,
) -> list[LayoutCandidate]:
    candidates: list[LayoutCandidate] = []

    for variant in range(variant_offset, variant_offset + count):
        graph_layout = place_room_graph(program=program, brief=brief, parti_decision=parti, variant=variant)
        refined = refine_layout(graph_layout, expected_area=program.target_area_sqm)

        merged_zones = dict(zones)
        merged_zones.update(refined.zone_map)

        candidates.append(
            LayoutCandidate(
                id=f"candidate_{variant + 1}",
                rooms=refined.rooms,
                walls=refined.walls,
                openings={"doors": [], "windows": []},
                fixtures=[],
                zones=merged_zones,
                circulation=refined.circulation,
                schedule=refined.schedule,
                score=ScoreBreakdown(
                    area_accuracy=0.0,
                    adjacency_quality=0.0,
                    zoning_quality=0.0,
                    privacy=0.0,
                    circulation_efficiency=0.0,
                    daylight_potential=0.0,
                    furniture_usability=0.0,
                    compactness=0.0,
                    wall_efficiency=0.0,
                    total=0.0,
                    explanation="Pending scoring",
                    grid_alignment_score=0.0,
                    hierarchy_score=0.0,
                    circulation_composition_score=0.0,
                    spatial_sequence_score=0.0,
                ),
                validation=ValidationReport(valid=False, errors=["Pending validation"], warnings=[]),
            )
        )

    return candidates
