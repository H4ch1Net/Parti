from app.services.brief_interpreter import interpret_brief


def test_interpret_brief_extracts_area_and_rooms():
    brief = interpret_brief("Make a floor plan for 2 bedrooms, kitchen, bathroom. 800 sqft")
    room_map = {r.type: r.count for r in brief.rooms}
    assert brief.target_area_sqft == 800
    assert room_map["bedroom"] == 2
    assert room_map["kitchen"] >= 1
    assert room_map["bathroom"] >= 1
    assert room_map["living"] >= 1
