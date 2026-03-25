from app.services.planner_pipeline import generate_from_prompt


def test_validation_report_and_scores_present():
    response = generate_from_prompt("Design a compact 2-bedroom apartment with open kitchen and good daylight around 900 sqft")
    candidate = response.candidates[0]
    assert candidate.validation is not None
    assert candidate.score.total > 0
    assert candidate.score.daylight_potential >= 0
    assert isinstance(candidate.validation.errors, list)
