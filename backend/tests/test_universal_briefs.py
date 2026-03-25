from app.services.planner_pipeline import generate_from_prompt


def _assert_valid(prompt: str):
    result = generate_from_prompt(prompt)
    best = next(c for c in result.candidates if c.id == result.best_candidate_id)
    assert best.validation.valid, best.validation.errors
    return best


def test_studio_apartment():
    best = _assert_valid("studio apartment 400 sqft")
    room_types = [r.type for r in best.rooms]
    assert "living" in room_types or "studio" in room_types


def test_small_residential():
    best = _assert_valid("800 sqft, 2 bedrooms, kitchen, bathroom")
    room_types = [r.type for r in best.rooms]
    assert room_types.count("bedroom") >= 2


def test_standard_residential():
    best = _assert_valid("3 bedroom 2 bathroom house 1200 sqft open plan")
    room_types = [r.type for r in best.rooms]
    assert room_types.count("bedroom") >= 3
    assert room_types.count("bathroom") >= 2


def test_large_residential():
    best = _assert_valid("4 bedroom 2.5 bathroom house 2000 sqft with master ensuite")
    room_types = [r.type for r in best.rooms]
    assert room_types.count("bedroom") >= 4
    assert "ensuite" in room_types or room_types.count("bathroom") >= 2


def test_commercial_small():
    best = _assert_valid("small office 600 sqft, reception, 3 private offices, bathroom")
    room_types = [r.type for r in best.rooms]
    assert "reception" in room_types
    assert room_types.count("private_office") >= 3


def test_multi_story():
    best = _assert_valid("two story house 1800 sqft, 3 bedrooms upstairs, living kitchen dining downstairs, 2 bathrooms")
    floors = {r.floor for r in best.rooms}
    assert len(floors) >= 2
    room_types = [r.type for r in best.rooms]
    assert room_types.count("bedroom") >= 3
