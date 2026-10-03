"""Room type catalog.

Single source of truth for everything the engine knows about a room type:
zoning, typical size, minimum dimensions, daylight needs and how it takes
part in circulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Band = Literal["front", "back", "either"]


@dataclass(frozen=True)
class RoomSpec:
    type: str
    label: str
    zone: str
    base_area: float  # typical size in sqm before scaling to the brief
    scale_exp: float  # how strongly the room grows with the overall area (0..1)
    min_area: float
    min_side: float  # shortest usable side in metres
    habitable: bool  # needs daylight
    band: Band  # preferred side of the plan: street front or private back
    serves: bool  # can act as circulation that other rooms open off
    open_plan: bool  # joins the open living cluster
    wet: bool = False
    door_width: float = 0.8
    max_aspect: float = 2.5


SPECS: dict[str, RoomSpec] = {
    s.type: s
    for s in [
        RoomSpec("entry", "Entry", "public", 4.0, 0.5, 2.5, 1.5, False, "front", True, True, door_width=0.9),
        RoomSpec("living", "Living", "public", 20.0, 1.0, 12.0, 3.3, True, "front", True, True),
        RoomSpec("studio", "Studio", "public", 24.0, 1.0, 16.0, 3.6, True, "front", True, True),
        RoomSpec("dining", "Dining", "public", 11.0, 0.9, 7.5, 2.7, True, "either", True, True),
        RoomSpec("kitchen", "Kitchen", "public", 10.0, 0.7, 6.0, 2.4, True, "either", True, True, wet=True),
        RoomSpec("bedroom", "Bedroom", "private", 12.0, 0.9, 8.5, 2.7, True, "back", False, False),
        RoomSpec("bathroom", "Bathroom", "private", 5.0, 0.4, 3.6, 1.8, False, "back", False, False, wet=True, door_width=0.7),
        RoomSpec("ensuite", "Ensuite", "private", 4.5, 0.4, 3.0, 1.5, False, "back", False, False, wet=True, door_width=0.7),
        RoomSpec("powder", "Powder room", "service", 2.5, 0.2, 1.8, 1.2, False, "either", False, False, wet=True, door_width=0.7),
        RoomSpec("corridor", "Hall", "circulation", 6.0, 0.0, 2.0, 1.0, False, "back", True, False, max_aspect=99.0),
        RoomSpec("stair", "Stair", "circulation", 5.0, 0.0, 3.5, 1.1, False, "back", True, False, max_aspect=5.0),
        RoomSpec("laundry", "Laundry", "service", 4.5, 0.4, 3.0, 1.5, False, "either", False, False, wet=True),
        RoomSpec("storage", "Storage", "service", 3.0, 0.3, 1.5, 1.2, False, "either", False, False, door_width=0.7),
        RoomSpec("garage", "Garage", "service", 20.0, 0.0, 18.0, 3.0, False, "front", False, False),
        RoomSpec("study", "Study", "private", 9.0, 0.7, 6.5, 2.4, True, "either", False, False),
        RoomSpec("reception", "Reception", "public", 14.0, 0.8, 9.0, 3.0, True, "front", True, True, door_width=0.9),
        RoomSpec("open_office", "Open office", "public", 30.0, 1.0, 18.0, 3.6, True, "either", True, False, door_width=0.9),
        RoomSpec("private_office", "Office", "private", 10.0, 0.7, 8.0, 2.7, True, "either", False, False, door_width=0.9),
        RoomSpec("meeting_room", "Meeting room", "public", 15.0, 0.8, 10.0, 3.0, True, "either", False, False, door_width=0.9),
        RoomSpec("break_room", "Break room", "service", 10.0, 0.6, 7.0, 2.4, True, "either", False, False, wet=True, door_width=0.9),
        RoomSpec("server_room", "Server room", "service", 5.0, 0.3, 3.5, 1.8, False, "back", False, False),
    ]
}

PRIMARY_BEDROOM_AREA = 14.0
PRIMARY_BEDROOM_MIN_SIDE = 3.0


def spec(room_type: str) -> RoomSpec:
    return SPECS[room_type]


def min_side(room_type: str, primary: bool = False) -> float:
    if room_type == "bedroom" and primary:
        return PRIMARY_BEDROOM_MIN_SIDE
    return SPECS[room_type].min_side


# Rooms that only make sense in one kind of building. Used by the UI program
# editor and to keep the interpreter from mixing programs.
RESIDENTIAL_TYPES = [
    "bedroom",
    "bathroom",
    "ensuite",
    "powder",
    "living",
    "dining",
    "kitchen",
    "study",
    "laundry",
    "storage",
    "garage",
    "entry",
    "studio",
]
COMMERCIAL_TYPES = [
    "reception",
    "open_office",
    "private_office",
    "meeting_room",
    "break_room",
    "bathroom",
    "storage",
    "server_room",
    "kitchen",
]


GARAGE_DEPTH = 5.4  # nose-in parking plus a walkway


def garage_fits(width: float, depth: float, cars: int) -> bool:
    """Whether a garage of this size holds ``cars`` parked side by side."""
    cars = max(1, cars)
    across = 2.5 * cars + 0.6 * (cars - 1) + 0.4
    return (width >= across - 1e-6 and depth >= GARAGE_DEPTH - 1e-6) or (depth >= across - 1e-6 and width >= GARAGE_DEPTH - 1e-6)
