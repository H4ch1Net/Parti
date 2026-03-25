from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.models.schemas import StructuredBrief


class Parti(str, Enum):
    OPEN_BAR = "open_bar"
    SPLIT_ZONE = "split_zone"
    LINEAR_BAR = "linear_bar"
    DOUBLE_LOADED = "double_loaded"
    CENTRAL_CORE = "central_core"
    L_SHAPE = "l_shape"


@dataclass
class ProgramBrief:
    total_area_sqm: float
    bedroom_count: int
    commercial: bool
    outdoor_space: bool
    entry_wall: str = "south"

    @staticmethod
    def from_structured(brief: StructuredBrief) -> "ProgramBrief":
        bedroom_count = 0
        for r in brief.rooms:
            if r.type == "bedroom":
                bedroom_count += r.count

        prompt = brief.raw_prompt.lower()
        outdoor_tokens = ("courtyard", "outdoor", "patio", "garden", "terrace")
        outdoor_space = any(t in prompt for t in outdoor_tokens)

        commercial_tokens = ("office", "reception", "meeting", "commercial", "workstation")
        has_commercial_prompt = any(t in prompt for t in commercial_tokens)

        return ProgramBrief(
            total_area_sqm=float(brief.target_area_sqm),
            bedroom_count=bedroom_count,
            commercial=(brief.building_type == "commercial" or has_commercial_prompt),
            outdoor_space=outdoor_space,
            entry_wall="south",
        )


@dataclass
class PartiDecision:
    parti: Parti
    circulation_pattern: str
    zone_layout: dict[str, str]
    grid_module: int


def _grid_module(total_area_sqm: float) -> int:
    if total_area_sqm < 100:
        return 900
    if total_area_sqm < 200:
        return 1200
    return 1500


def _decision(parti: Parti, total_area_sqm: float) -> PartiDecision:
    presets = {
        Parti.OPEN_BAR: (
            "open",
            {"public_side": "entry", "private_side": "far_end", "service_position": "end_pod"},
        ),
        Parti.SPLIT_ZONE: (
            "cross",
            {"public_side": "entry_side", "private_side": "opposite_side", "service_position": "middle"},
        ),
        Parti.LINEAR_BAR: (
            "spine",
            {"public_side": "entry_side", "private_side": "corridor_side", "service_position": "along_spine"},
        ),
        Parti.DOUBLE_LOADED: (
            "spine",
            {"public_side": "entry_half", "private_side": "rear_half", "service_position": "core_bands"},
        ),
        Parti.CENTRAL_CORE: (
            "perimeter",
            {"public_side": "entry_front", "private_side": "perimeter", "service_position": "center"},
        ),
        Parti.L_SHAPE: (
            "perimeter",
            {"public_side": "short_leg", "private_side": "long_leg", "service_position": "inner_corner"},
        ),
    }
    circulation_pattern, zone_layout = presets[parti]
    return PartiDecision(
        parti=parti,
        circulation_pattern=circulation_pattern,
        zone_layout=zone_layout,
        grid_module=_grid_module(total_area_sqm),
    )


def select_parti(brief: ProgramBrief) -> PartiDecision:
    # Commercial must override small-area/open-plan residential defaults.
    if brief.commercial:
        return _decision(Parti.CENTRAL_CORE, brief.total_area_sqm)

    # Large projects with intentional outdoor intent use corner-wrapping organization.
    if brief.outdoor_space:
        return _decision(Parti.L_SHAPE, brief.total_area_sqm)

    if brief.bedroom_count >= 4 or brief.total_area_sqm >= 180:
        return _decision(Parti.DOUBLE_LOADED, brief.total_area_sqm)

    if brief.bedroom_count >= 3 or brief.total_area_sqm >= 120:
        return _decision(Parti.LINEAR_BAR, brief.total_area_sqm)

    if brief.bedroom_count == 2 and brief.total_area_sqm < 120:
        return _decision(Parti.SPLIT_ZONE, brief.total_area_sqm)

    if brief.total_area_sqm < 60 or brief.bedroom_count <= 1:
        return _decision(Parti.OPEN_BAR, brief.total_area_sqm)

    if brief.total_area_sqm >= 200:
        return _decision(Parti.L_SHAPE, brief.total_area_sqm)

    return _decision(Parti.SPLIT_ZONE, brief.total_area_sqm)
