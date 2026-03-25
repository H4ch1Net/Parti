from app.services.planner_pipeline import generate_from_prompt


def test_golden_prompt_800sqft_two_bed_kitchen_bathroom():
    result = generate_from_prompt("800 sqft, 2 bedrooms, kitchen, bathroom")
    best = next(c for c in result.candidates if c.id == result.best_candidate_id)
    assert best.validation.valid
    room_types = [r.type for r in best.rooms]
    assert room_types.count("bedroom") >= 2
    assert "kitchen" in room_types
    assert "bathroom" in room_types
    assert any(best.openings["doors"])
    assert any(best.openings["windows"])
