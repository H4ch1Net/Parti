"""Metric and imperial formatting for drawings and exports."""

from __future__ import annotations

SQFT_PER_SQM = 10.7639


def feet_inches(m: float) -> str:
    inches = round(m / 0.0254)
    feet, rem = divmod(inches, 12)
    return f"{feet}'-{rem}\""


def length(m: float, units: str) -> str:
    return feet_inches(m) if units == "imperial" else f"{m:.2f}"


def area(sqm: float, units: str) -> str:
    return f"{sqm * SQFT_PER_SQM:,.0f} ft²" if units == "imperial" else f"{sqm:.1f} m²"


def dims(w: float, d: float, units: str) -> str:
    if units == "imperial":
        return f"{feet_inches(w)} × {feet_inches(d)}"
    return f"{w:.1f} × {d:.1f}"
