"""API and engine data models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

SQM_TO_SQFT = 10.7639

RoomType = Literal[
    "entry",
    "living",
    "studio",
    "dining",
    "kitchen",
    "bedroom",
    "bathroom",
    "ensuite",
    "powder",
    "corridor",
    "stair",
    "laundry",
    "storage",
    "garage",
    "study",
    "reception",
    "open_office",
    "private_office",
    "meeting_room",
    "break_room",
    "server_room",
]
Zone = Literal["public", "private", "service", "circulation"]
Point = list[float]


# ---------------------------------------------------------------- brief ----


class RoomRequest(BaseModel):
    type: RoomType
    count: int = Field(default=1, ge=0, le=12)


class Preferences(BaseModel):
    daylight: bool = False
    privacy: bool = False
    compact: bool = False


class StructuredBrief(BaseModel):
    raw_prompt: str = Field(default="", max_length=2000)
    building_type: Literal["residential", "commercial"] = "residential"
    target_area_sqm: float = Field(ge=15, le=1500)
    area_source: Literal["stated", "estimated"] = "estimated"
    stories: int = Field(default=1, ge=1, le=3)
    style: Literal["open_plan", "traditional"] = "open_plan"
    rooms: list[RoomRequest]
    preferences: Preferences = Field(default_factory=Preferences)
    notes: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def target_area_sqft(self) -> float:
        return round(self.target_area_sqm * SQM_TO_SQFT, 1)

    def count(self, room_type: str) -> int:
        return sum(r.count for r in self.rooms if r.type == room_type)

    @model_validator(mode="after")
    def _limit_rooms(self) -> StructuredBrief:
        if sum(r.count for r in self.rooms) > 40:
            raise ValueError("A brief may contain at most 40 rooms")
        return self


# -------------------------------------------------------------- program ----


class ProgramRoom(BaseModel):
    id: str
    type: RoomType
    name: str
    zone: Zone
    floor: int = 1
    target_area_sqm: float
    min_area_sqm: float
    primary: bool = False


class AdjacencyPreference(BaseModel):
    a: str
    b: str
    weight: float


class Program(BaseModel):
    target_area_sqm: float
    stories: int
    rooms: list[ProgramRoom]
    adjacency: list[AdjacencyPreference]


# ------------------------------------------------------------ candidate ----


class Room(BaseModel):
    id: str
    type: RoomType
    name: str
    zone: Zone
    floor: int
    polygon: list[Point]
    width_m: float
    depth_m: float
    area_sqm: float
    target_area_sqm: float
    primary: bool = False


class Wall(BaseModel):
    id: str
    floor: int
    segment: list[Point]
    thickness: float
    exterior: bool


class Door(BaseModel):
    """A connection cut into a wall.

    ``kind`` is ``entry`` (front door), ``door`` (swing door), ``opening``
    (cased opening with no leaf) or ``garage`` (overhead door). For swing
    doors ``hinge`` is the pivot and ``swing`` the leaf tip when fully open.
    """

    id: str
    kind: Literal["entry", "door", "opening", "garage"]
    floor: int
    room_a: str
    room_b: str
    segment: list[Point]
    width: float
    hinge: Point | None = None
    swing: Point | None = None


class Window(BaseModel):
    id: str
    room_id: str
    floor: int
    segment: list[Point]
    width: float


class Fixture(BaseModel):
    id: str
    room_id: str
    floor: int
    type: str
    footprint: list[Point]
    facing: Literal["n", "s", "e", "w"] = "n"


class Connection(BaseModel):
    from_room: str
    to_room: str
    kind: Literal["door", "opening", "stair"]
    length_m: float


class ScoreCategory(BaseModel):
    key: str
    label: str
    score: float
    weight: float
    detail: str


class Score(BaseModel):
    total: float
    grade: Literal["excellent", "good", "fair", "weak"]
    categories: list[ScoreCategory]
    summary: str

    def category(self, key: str) -> ScoreCategory:
        return next(c for c in self.categories if c.key == key)


class Issue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    room_ids: list[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    valid: bool
    issues: list[Issue] = Field(default_factory=list)

    @property
    def errors(self) -> list[str]:
        return [i.message for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[str]:
        return [i.message for i in self.issues if i.severity == "warning"]


class Footprint(BaseModel):
    width_m: float
    depth_m: float

    @computed_field  # type: ignore[prop-decorator]
    @property
    def area_sqm(self) -> float:
        return round(self.width_m * self.depth_m, 2)


class Candidate(BaseModel):
    id: str
    label: str
    strategy: str
    floors: int
    footprint: Footprint
    rooms: list[Room]
    walls: list[Wall]
    doors: list[Door]
    windows: list[Window]
    fixtures: list[Fixture]
    connections: list[Connection]
    zones: dict[str, list[str]]
    score: Score
    validation: ValidationReport

    @property
    def total_area_sqm(self) -> float:
        return sum(r.area_sqm for r in self.rooms)


# ------------------------------------------------------------------ API ----


class InterpretRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


class GenerateRequest(BaseModel):
    prompt: str | None = Field(default=None, max_length=2000)
    brief: StructuredBrief | None = None
    count: int = Field(default=6, ge=1, le=12)

    @model_validator(mode="after")
    def _need_input(self) -> GenerateRequest:
        if self.brief is None and not (self.prompt and self.prompt.strip()):
            raise ValueError("Provide either a prompt or a structured brief")
        return self


class GenerateResponse(BaseModel):
    brief: StructuredBrief
    program: Program
    candidates: list[Candidate]
    best_candidate_id: str
    drawings: dict[str, list[str]] = Field(default_factory=dict, description="Inline SVG per candidate id, one entry per floor")
    elapsed_ms: int = 0


class ValidateRequest(BaseModel):
    candidate: Candidate
    target_area_sqm: float | None = None


class ExportRequest(BaseModel):
    candidate: Candidate
    units: Literal["metric", "imperial"] = "metric"
    title: str | None = Field(default=None, max_length=120)
