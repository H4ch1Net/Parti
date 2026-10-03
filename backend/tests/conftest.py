from __future__ import annotations

from functools import lru_cache

from app.engine.pipeline import generate_from_prompt
from app.models.schemas import Candidate, GenerateResponse


@lru_cache(maxsize=64)
def generated(prompt: str) -> GenerateResponse:
    """Generation is deterministic, so tests share results per prompt."""
    return generate_from_prompt(prompt)


def best(prompt: str) -> Candidate:
    result = generated(prompt)
    return next(c for c in result.candidates if c.id == result.best_candidate_id)
