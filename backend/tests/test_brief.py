import pytest

from app.engine.brief import interpret_brief


def counts(prompt: str) -> dict[str, int]:
    return {r.type: r.count for r in interpret_brief(prompt).rooms}


def test_golden_prompt():
    brief = interpret_brief("Make a floor plan for 2 bedrooms, kitchen, bathroom. 800 sqft")
    room = counts(brief.raw_prompt)
    assert brief.target_area_sqft == pytest.approx(800, abs=1)
    assert brief.area_source == "stated"
    assert room["bedroom"] == 2 and room["kitchen"] == 1 and room["bathroom"] == 1
    assert room["living"] == 1 and room["entry"] == 1


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("compact 2-bedroom apartment", {"bedroom": 2}),
        ("three bedroom home", {"bedroom": 3}),
        ("3 bed 2 bath", {"bedroom": 3, "bathroom": 2}),
        ("3br/2ba ranch", {"bedroom": 3, "bathroom": 2}),
        ("two bedrooms, one bath flat", {"bedroom": 2, "bathroom": 1}),
        ("an extra bedroom", {"bedroom": 1}),
    ],
)
def test_room_counts(prompt, expected):
    got = counts(prompt)
    for rtype, n in expected.items():
        assert got[rtype] == n, (prompt, got)


def test_half_baths_become_powder_rooms():
    got = counts("4 bedroom 2.5 bathroom house")
    assert got["bathroom"] == 2 and got["powder"] == 1


def test_ensuite_counts_against_bathrooms():
    got = counts("4 bedroom 2.5 bath house with master ensuite")
    assert got["ensuite"] == 1 and got["bathroom"] == 1 and got["powder"] == 1


@pytest.mark.parametrize(
    "prompt,sqm",
    [
        ("house, 1,200 sq ft", 111.5),
        ("1200 square feet", 111.5),
        ("85 m2 flat", 85.0),
        ("85 m² flat", 85.0),
        ("a 70 sqm apartment", 70.0),
        ("120 square metres", 120.0),
    ],
)
def test_area_units(prompt, sqm):
    assert interpret_brief(prompt).target_area_sqm == pytest.approx(sqm, abs=0.2)


def test_missing_area_is_estimated_and_noted():
    brief = interpret_brief("2 bedroom apartment")
    assert brief.area_source == "estimated"
    assert 50 < brief.target_area_sqm < 110
    assert any("estimated" in n for n in brief.notes)


def test_home_office_stays_residential():
    brief = interpret_brief("3 bedroom house with a home office")
    assert brief.building_type == "residential"
    assert counts(brief.raw_prompt)["study"] == 1


def test_commercial_brief():
    brief = interpret_brief("small office 600 sqft, reception, 3 private offices, bathroom")
    got = counts(brief.raw_prompt)
    assert brief.building_type == "commercial"
    assert got["reception"] == 1 and got["private_office"] == 3 and got["bathroom"] == 1
    assert "bedroom" not in got


def test_office_for_people_gets_open_office():
    got = counts("office for 12 people with 2 meeting rooms")
    assert got["open_office"] == 1 and got["meeting_room"] == 2 and "private_office" not in got


def test_studio_has_no_bedroom():
    got = counts("studio apartment 400 sqft")
    assert got["studio"] == 1 and "bedroom" not in got and "living" not in got


def test_stories_and_garage():
    brief = interpret_brief("two-storey house with a 2-car garage, 3 bedrooms")
    assert brief.stories == 2
    assert counts(brief.raw_prompt)["garage"] == 2


@pytest.mark.parametrize(
    "prompt,style",
    [("open plan 2 bed", "open_plan"), ("traditional 3 bed house", "traditional"), ("2 bed with separate kitchen", "traditional")],
)
def test_style(prompt, style):
    assert interpret_brief(prompt).style == style
