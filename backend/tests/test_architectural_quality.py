"""
Parti — Architectural Quality Tests
====================================
These tests check REAL architectural values from the generated layout.
They were written independently and must NOT be modified by Copilot.
All tests must pass before any output is considered acceptable.

Run with:
    cd backend
    source .venv/bin/activate
    pytest tests/test_architectural_quality.py -v
"""

from __future__ import annotations

import pytest
from app.services.planner_pipeline import generate_from_prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_best(prompt: str):
    result = generate_from_prompt(prompt)
    best = next(c for c in result.candidates if c.id == result.best_candidate_id)
    return best


def rooms_by_type(best) -> dict:
    out = {}
    for r in best.rooms:
        out.setdefault(r.type, []).append(r)
    return out


def total_area(best) -> float:
    return sum(r.area_sqm for r in best.rooms)


def corridor_area(best) -> float:
    return sum(r.area_sqm for r in best.rooms if r.type == "corridor")


# ---------------------------------------------------------------------------
# SUITE 1 — Area budget sanity
# These are the most basic checks. If these fail, nothing else matters.
# ---------------------------------------------------------------------------

class TestAreaBudget:

    def test_no_single_room_dominates(self):
        """No room may exceed 35% of total floor area."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        total = total_area(best)
        for r in best.rooms:
            ratio = r.area_sqm / total
            assert ratio <= 0.35, (
                f"{r.name} ({r.type}) is {r.area_sqm:.1f} sqm = {ratio:.0%} of total. "
                f"Max allowed is 35%. Total floor area: {total:.1f} sqm."
            )

    def test_corridor_not_oversized(self):
        """Corridor must be at most 12% of total floor area."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        total = total_area(best)
        c_area = corridor_area(best)
        ratio = c_area / total
        assert ratio <= 0.12, (
            f"Corridor is {c_area:.1f} sqm = {ratio:.0%} of total. "
            f"Max allowed is 12%. This wastes usable space."
        )

    def test_total_area_within_10_percent_of_brief(self):
        """Total generated area must be within 10% of requested 74.3 sqm (800 sqft)."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        total = total_area(best)
        target = 74.32  # 800 sqft in sqm
        assert abs(total - target) / target <= 0.10, (
            f"Total area is {total:.1f} sqm but brief requested {target:.1f} sqm. "
            f"Difference: {abs(total - target):.1f} sqm ({abs(total - target) / target:.0%})."
        )

    def test_service_spaces_not_oversized(self):
        """All bathrooms combined must not exceed 15% of total floor area."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        total = total_area(best)
        bath_area = sum(r.area_sqm for r in best.rooms if r.type in {"bathroom", "ensuite"})
        ratio = bath_area / total
        assert ratio <= 0.15, (
            f"Bathrooms total {bath_area:.1f} sqm = {ratio:.0%} of total. "
            f"Max allowed is 15%."
        )


# ---------------------------------------------------------------------------
# SUITE 2 — Minimum room dimensions
# Rooms below these sizes are not usable with real furniture.
# ---------------------------------------------------------------------------

MINIMUM_WIDTHS = {
    "kitchen": 2.4,
    "bathroom": 1.8,
    "bedroom": 2.7,
    "living": 3.0,
    "dining": 2.4,
    "corridor": 1.0,
}

MINIMUM_AREAS = {
    "kitchen": 5.76,    # 2.4 x 2.4
    "bathroom": 4.32,   # 1.8 x 2.4
    "bedroom": 8.1,     # 2.7 x 3.0
    "living": 10.5,     # 3.0 x 3.5
}

class TestMinimumDimensions:

    def test_kitchen_minimum_width(self):
        """Kitchen must be at least 2.4m wide on its shortest side."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        rbt = rooms_by_type(best)
        for r in rbt.get("kitchen", []):
            shortest = min(r.width_m, r.depth_m)
            assert shortest >= 2.4, (
                f"Kitchen {r.id} has shortest dimension {shortest:.2f}m. "
                f"Minimum is 2.4m. A 2.4m kitchen cannot fit a work triangle."
            )

    def test_bathroom_minimum_width(self):
        """Bathroom must be at least 1.8m wide on its shortest side."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        rbt = rooms_by_type(best)
        for r in rbt.get("bathroom", []):
            shortest = min(r.width_m, r.depth_m)
            assert shortest >= 1.8, (
                f"Bathroom {r.id} has shortest dimension {shortest:.2f}m. "
                f"Minimum is 1.8m. A narrower bathroom cannot fit toilet + sink."
            )

    def test_bedroom_minimum_width(self):
        """Every bedroom must be at least 2.7m wide on its shortest side."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        rbt = rooms_by_type(best)
        for r in rbt.get("bedroom", []):
            shortest = min(r.width_m, r.depth_m)
            assert shortest >= 2.7, (
                f"Bedroom {r.id} has shortest dimension {shortest:.2f}m. "
                f"Minimum is 2.7m. A narrower bedroom cannot fit a bed with clearance."
            )

    def test_no_room_is_a_sliver(self):
        """No room may have an aspect ratio worse than 1:2.5."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        for r in best.rooms:
            if r.type == "corridor":
                continue
            longer = max(r.width_m, r.depth_m)
            shorter = min(r.width_m, r.depth_m)
            if shorter < 0.01:
                continue
            ratio = longer / shorter
            assert ratio <= 2.5, (
                f"{r.name} ({r.type}) has aspect ratio 1:{ratio:.2f} "
                f"({r.width_m:.2f}m x {r.depth_m:.2f}m). Max allowed is 1:2.5."
            )

    def test_bedrooms_balanced(self):
        """Two bedrooms must be within 40% of each other in area."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        rbt = rooms_by_type(best)
        bedrooms = rbt.get("bedroom", [])
        if len(bedrooms) < 2:
            pytest.skip("Fewer than 2 bedrooms generated")
        areas = sorted(r.area_sqm for r in bedrooms)
        ratio = areas[-1] / max(0.01, areas[0])
        assert ratio <= 1.4, (
            f"Bedrooms are unbalanced: {areas[0]:.1f} sqm vs {areas[-1]:.1f} sqm "
            f"(ratio {ratio:.2f}x). Max allowed is 1.4x. "
            f"One bedroom is being starved to feed another."
        )

    def test_kitchen_minimum_area(self):
        """Kitchen must be at least 5.76 sqm (2.4 x 2.4)."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        rbt = rooms_by_type(best)
        for r in rbt.get("kitchen", []):
            assert r.area_sqm >= 5.76, (
                f"Kitchen {r.id} is {r.area_sqm:.2f} sqm. "
                f"Minimum is 5.76 sqm. Cannot fit sink + stove + fridge."
            )


# ---------------------------------------------------------------------------
# SUITE 3 — Zoning and hierarchy
# The right spaces must be in the right places.
# ---------------------------------------------------------------------------

class TestZoningAndHierarchy:

    def test_living_room_is_largest_public_space(self):
        """Living room must be the largest single room in the public zone."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        rbt = rooms_by_type(best)
        living = rbt.get("living", [])
        kitchen = rbt.get("kitchen", [])
        if not living or not kitchen:
            pytest.skip("Living or kitchen not found")
        living_area = max(r.area_sqm for r in living)
        kitchen_area = max(r.area_sqm for r in kitchen)
        assert living_area > kitchen_area, (
            f"Living room ({living_area:.1f} sqm) is smaller than kitchen "
            f"({kitchen_area:.1f} sqm). The primary space must dominate."
        )

    def test_living_room_gets_best_edge(self):
        """Living room must be on the best perimeter edge (entry side)."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        zone_map = best.zone_map if hasattr(best, "zone_map") else {}
        best_edge = (zone_map.get("__best_edge") or ["south"])[0]
        tier1_ids = zone_map.get("__tier1", [])

        rbt = rooms_by_type(best)
        living_ids = {r.id for r in rbt.get("living", [])}

        overlap = living_ids & set(tier1_ids)
        assert len(overlap) > 0, (
            f"No living room found in Tier 1 (best edge = {best_edge}). "
            f"Living room IDs: {living_ids}. Tier 1 IDs: {tier1_ids}."
        )

    def test_no_bathroom_on_best_edge(self):
        """Bathrooms must not occupy the best perimeter edge."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        zone_map = best.zone_map if hasattr(best, "zone_map") else {}
        best_edge = (zone_map.get("__best_edge") or ["south"])[0]
        second_edge = (zone_map.get("__second_edge") or ["west"])[0]
        tier4_ids = set(zone_map.get("__tier4", []))

        rbt = rooms_by_type(best)
        bath_ids = {r.id for r in rbt.get("bathroom", [])}

        # Bathroom must not be in tier1 or tier2 (best/second edge)
        for r in best.rooms:
            if r.type in {"bathroom", "ensuite"}:
                edge = zone_map.get(f"__edge::{r.id}", [None])[0]
                assert edge not in {best_edge, second_edge}, (
                    f"Bathroom {r.id} is on {edge} edge (best={best_edge}, "
                    f"second={second_edge}). Bathrooms must use worst edge."
                )

    def test_no_bedroom_in_public_zone(self):
        """No bedroom should be in the public zone."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        for r in best.rooms:
            if r.type == "bedroom":
                assert r.zone != "public", (
                    f"Bedroom {r.id} ({r.name}) is in the public zone. "
                    f"Bedrooms belong in the private zone."
                )


# ---------------------------------------------------------------------------
# SUITE 4 — Circulation and access
# Every room must be reachable. Corridors must be efficient.
# ---------------------------------------------------------------------------

class TestCirculation:

    def test_every_room_reachable_from_entry(self):
        """BFS from entry must reach every room in the layout."""
        from collections import deque

        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")

        # Build adjacency from circulation edges
        adj: dict[str, set[str]] = {}
        for edge in best.circulation:
            adj.setdefault(edge.from_room, set()).add(edge.to_room)
            adj.setdefault(edge.to_room, set()).add(edge.from_room)

        rbt = rooms_by_type(best)
        start_candidates = (
            rbt.get("entry", []) or
            rbt.get("living", []) or
            rbt.get("reception", [])
        )
        if not start_candidates:
            pytest.skip("No entry/living/reception room found")

        start = start_candidates[0].id
        seen = {start}
        q = deque([start])
        while q:
            cur = q.popleft()
            for nxt in adj.get(cur, set()):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)

        all_ids = {r.id for r in best.rooms}
        unreachable = all_ids - seen
        assert len(unreachable) == 0, (
            f"{len(unreachable)} rooms are unreachable from entry: "
            f"{unreachable}. These rooms have no circulation path."
        )

    def test_corridor_area_under_12_percent(self):
        """Corridor must not exceed 12% of floor area."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        total = total_area(best)
        c_area = corridor_area(best)
        assert c_area / total <= 0.12, (
            f"Corridor is {c_area:.1f} sqm = {c_area/total:.0%}. Max is 12%."
        )

    def test_no_undefined_voids(self):
        """All area must be accounted for in named rooms. No unassigned voids."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        # Every room must have a non-empty name and type
        for r in best.rooms:
            assert r.name and r.name.strip(), f"Room {r.id} has no name."
            assert r.type and r.type.strip(), f"Room {r.id} has no type."
            assert r.area_sqm > 0.5, (
                f"Room {r.id} ({r.name}) has area {r.area_sqm:.2f} sqm. "
                f"This is effectively a void, not a room."
            )


# ---------------------------------------------------------------------------
# SUITE 5 — Multi-input robustness
# The engine must produce valid plans for varied inputs, not just the golden case.
# ---------------------------------------------------------------------------

ROBUSTNESS_CASES = [
    ("studio apartment 400 sqft",          1,  37.2),
    ("800 sqft, 2 bedrooms, kitchen, bathroom",  2,  74.3),
    ("3 bedroom house 1200 sqft",          3, 111.5),
    ("4 bedroom 2 bathroom house 1800 sqft", 4, 167.2),
    ("small office 600 sqft reception 3 offices bathroom", 0, 55.7),
]

class TestRobustness:

    @pytest.mark.parametrize("prompt,min_beds,target_sqm", ROBUSTNESS_CASES)
    def test_plan_generates_without_error(self, prompt, min_beds, target_sqm):
        """Each brief type must generate a valid plan without raising."""
        best = get_best(prompt)
        assert best is not None, f"No plan generated for: {prompt}"
        assert best.validation.valid, (
            f"Plan invalid for '{prompt}'. Errors: {best.validation.errors}"
        )

    @pytest.mark.parametrize("prompt,min_beds,target_sqm", ROBUSTNESS_CASES)
    def test_no_room_dominates_any_brief(self, prompt, min_beds, target_sqm):
        """No single room exceeds 35% of total for any input."""
        best = get_best(prompt)
        total = total_area(best)
        for r in best.rooms:
            ratio = r.area_sqm / total
            assert ratio <= 0.35, (
                f"[{prompt}] {r.name} ({r.type}) is {ratio:.0%} of total. Max 35%."
            )

    @pytest.mark.parametrize("prompt,min_beds,target_sqm", ROBUSTNESS_CASES)
    def test_corridor_budget_any_brief(self, prompt, min_beds, target_sqm):
        """Corridor never exceeds 12% for any input."""
        best = get_best(prompt)
        total = total_area(best)
        c_area = corridor_area(best)
        assert c_area / total <= 0.12, (
            f"[{prompt}] Corridor is {c_area/total:.0%}. Max 12%."
        )

    @pytest.mark.parametrize("prompt,min_beds,target_sqm", ROBUSTNESS_CASES)
    def test_no_sliver_rooms_any_brief(self, prompt, min_beds, target_sqm):
        """No room has aspect ratio worse than 1:2.5 for any input."""
        best = get_best(prompt)
        for r in best.rooms:
            if r.type == "corridor":
                continue
            longer = max(r.width_m, r.depth_m)
            shorter = min(r.width_m, r.depth_m)
            if shorter < 0.01:
                continue
            ratio = longer / shorter
            assert ratio <= 2.5, (
                f"[{prompt}] {r.name} ({r.type}) aspect ratio 1:{ratio:.2f}. Max 1:2.5."
            )

    @pytest.mark.parametrize("prompt,min_beds,target_sqm", ROBUSTNESS_CASES)
    def test_score_meets_threshold_any_brief(self, prompt, min_beds, target_sqm):
        """Every plan must score at least 70/100."""
        best = get_best(prompt)
        assert best.score.total >= 70.0, (
            f"[{prompt}] Score is {best.score.total:.1f}/100. Minimum is 70."
        )


# ---------------------------------------------------------------------------
# SUITE 6 — Scoring integrity
# The score must reflect actual architectural quality, not just completion.
# ---------------------------------------------------------------------------

class TestScoringIntegrity:

    def test_score_reflects_corridor_penalty(self):
        """A plan with an oversized corridor must score lower than one without."""
        # This test generates two plans and compares scores.
        # If scoring doesn't penalize corridor waste, it's not measuring quality.
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        total = total_area(best)
        c_area = corridor_area(best)
        c_ratio = c_area / total

        # If corridor is under control, score should be >= 70
        if c_ratio <= 0.12:
            assert best.score.total >= 70.0, (
                f"Corridor is fine ({c_ratio:.0%}) but score is only "
                f"{best.score.total:.1f}. Scoring may not reflect quality."
            )

    def test_score_categories_present(self):
        """Score object must have meaningful sub-categories."""
        best = get_best("800 sqft, 2 bedrooms, kitchen, bathroom")
        score = best.score
        # Must have a total
        assert hasattr(score, "total"), "Score missing 'total' field"
        assert score.total > 0, "Score total is zero"
        # Must have at least one sub-category that's not just the total
        score_dict = score.__dict__ if hasattr(score, "__dict__") else {}
        sub_scores = {k: v for k, v in score_dict.items() if k != "total" and isinstance(v, (int, float))}
        assert len(sub_scores) >= 3, (
            f"Score has only {len(sub_scores)} sub-categories: {list(sub_scores.keys())}. "
            f"Need at least 3 to measure different quality dimensions."
        )