from app.services.planner_pipeline import generate_from_prompt


def test_generate_pipeline_returns_candidates_and_best():
    response = generate_from_prompt("800 sqft, 2 bedrooms, kitchen, bathroom")
    assert len(response.candidates) >= 5
    assert response.best_candidate_id in {c.id for c in response.candidates}
    assert all(c.score.total >= 0 for c in response.candidates)
