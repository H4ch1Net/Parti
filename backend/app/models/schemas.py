from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

class RoomRequest(BaseModel):
    type: str
    count: int = Field(default=1, ge=1, le=12)


class Preferences(BaseModel):
    open_kitchen: bool = False
    privacy: bool = False
    compact: bool = False
    daylight: bool = True
    efficient_circulation: bool = True


class BriefRequest(BaseModel):
    prompt: str = Field(min_length=3)


class StructuredBrief(BaseModel):
    raw_prompt: str
    target_area_sqft: float
    target_area_sqm: float
    rooms: list[RoomRequest]
    preferences: Preferences
    building_type: Literal["residential", "commercial", "mixed"] = "residential"
    story_count: int = 1
    style_preference: Literal["open_plan", "traditional"] = "open_plan"
    explicit_adjacency: list[tuple[str, str]] = Field(default_factory=list)


class ProgramRoom(BaseModel):
    id: str
    type: str
    name: str
    zone: Literal["public", "private", "service", "circulation"]
    target_area_sqm: float
    min_area_sqm: float
    floor: int = 1


class ProgramOutput(BaseModel):
    target_area_sqm: float
    rooms: list[ProgramRoom]
    adjacency_matrix: dict[str, dict[str, float]]


class DoorGeometry(BaseModel):
    id: str
    room_a: str
    room_b: str
    wall_segment: list[list[float]]
    hinge: list[float]
    leaf_end: list[float]
    swing_radius: float
    width: float


class WindowGeometry(BaseModel):
    id: str
    room_id: str
    wall_segment: list[list[float]]
    width: float


class Fixture(BaseModel):
    id: str
    room_id: str
    type: str
    footprint: list[list[float]]


class RoomGeometry(BaseModel):
    id: str
    type: str
    name: str
    zone: str
    polygon: list[list[float]]
    area_sqm: float
    width_m: float
    depth_m: float
    floor: int = 1


class Wall(BaseModel):
    id: str
    room_id: str
    segment: list[list[float]]
    thickness: float
    exterior: bool


class CirculationEdge(BaseModel):
    from_room: str
    to_room: str
    length_m: float


class ScoreBreakdown(BaseModel):
    area_accuracy: float
    adjacency_quality: float
    zoning_quality: float
    privacy: float
    circulation_efficiency: float
    daylight_potential: float
    furniture_usability: float
    compactness: float
    wall_efficiency: float
    total: float
    explanation: str
    grid_alignment_score: float = 0.0
    hierarchy_score: float = 0.0
    circulation_composition_score: float = 0.0
    spatial_sequence_score: float = 0.0


class ValidationReport(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RoomScheduleRow(BaseModel):
    room_name: str
    room_type: str
    area_sqm: float
    dimensions_m: str


class LayoutCandidate(BaseModel):
    id: str
    rooms: list[RoomGeometry]
    walls: list[Wall]
    openings: dict[str, list[Any]]
    fixtures: list[Fixture]
    zones: dict[str, list[str]]
    circulation: list[CirculationEdge]
    schedule: list[RoomScheduleRow]
    score: ScoreBreakdown
    validation: ValidationReport


class GenerateResponse(BaseModel):
    brief: StructuredBrief
    program: ProgramOutput
    candidates: list[LayoutCandidate]
    best_candidate_id: str


class ValidateRequest(BaseModel):
    candidate: LayoutCandidate


class ExportRequest(BaseModel):
    candidate: LayoutCandidate


class ParseResponse(BaseModel):
    walls: list[list[list[float]]]
    room_polygons: list[list[list[float]]]
    labels: list[str]
