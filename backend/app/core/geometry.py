"""Axis-aligned geometry helpers.

Every room in a Parti plan is an axis-aligned rectangle, so the engine works
with small value types instead of a general polygon library.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

EPS = 1e-6


def r3(v: float) -> float:
    return round(float(v), 3)


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    @cached_property
    def x1(self) -> float:
        return r3(self.x + self.w)

    @cached_property
    def y1(self) -> float:
        return r3(self.y + self.h)

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def short(self) -> float:
        return min(self.w, self.h)

    @property
    def long(self) -> float:
        return max(self.w, self.h)

    @property
    def aspect(self) -> float:
        return self.long / max(self.short, EPS)

    def polygon(self) -> list[list[float]]:
        return [
            [r3(self.x), r3(self.y)],
            [self.x1, r3(self.y)],
            [self.x1, self.y1],
            [r3(self.x), self.y1],
        ]

    def inset(self, left: float, bottom: float, right: float, top: float) -> Box:
        return Box(self.x + left, self.y + bottom, self.w - left - right, self.h - bottom - top)

    def intersects(self, other: Box, tol: float = EPS) -> bool:
        return (
            self.x < other.x + other.w - tol
            and other.x < self.x + self.w - tol
            and self.y < other.y + other.h - tol
            and other.y < self.y + self.h - tol
        )

    def contains(self, other: Box, tol: float = 1e-4) -> bool:
        return (
            other.x >= self.x - tol
            and other.y >= self.y - tol
            and other.x + other.w <= self.x + self.w + tol
            and other.y + other.h <= self.y + self.h + tol
        )

    def contains_point(self, x: float, y: float, tol: float = 1e-4) -> bool:
        return self.x - tol <= x <= self.x + self.w + tol and self.y - tol <= y <= self.y + self.h + tol


@dataclass(frozen=True)
class Segment:
    """Axis-aligned segment. ``horizontal`` segments run along x at constant y."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def horizontal(self) -> bool:
        return abs(self.y0 - self.y1) < EPS

    @property
    def length(self) -> float:
        return abs(self.x1 - self.x0) + abs(self.y1 - self.y0)

    @property
    def lo(self) -> float:
        return min(self.x0, self.x1) if self.horizontal else min(self.y0, self.y1)

    @property
    def hi(self) -> float:
        return max(self.x0, self.x1) if self.horizontal else max(self.y0, self.y1)

    @property
    def offset(self) -> float:
        """The constant coordinate (y for horizontal, x for vertical)."""
        return self.y0 if self.horizontal else self.x0

    def point(self, t: float) -> tuple[float, float]:
        """Point at absolute coordinate ``t`` along the segment axis."""
        return (t, self.offset) if self.horizontal else (self.offset, t)

    def sub(self, lo: float, hi: float) -> Segment:
        if self.horizontal:
            return Segment(r3(lo), self.offset, r3(hi), self.offset)
        return Segment(self.offset, r3(lo), self.offset, r3(hi))

    def as_list(self) -> list[list[float]]:
        return [[r3(self.x0), r3(self.y0)], [r3(self.x1), r3(self.y1)]]


SIDES = ("s", "e", "n", "w")
# Inward normal of each side of a box (pointing into the room).
NORMALS = {"s": (0.0, 1.0), "n": (0.0, -1.0), "w": (1.0, 0.0), "e": (-1.0, 0.0)}


def side_segment(b: Box, side: str) -> Segment:
    if side == "s":
        return Segment(r3(b.x), r3(b.y), b.x1, r3(b.y))
    if side == "n":
        return Segment(r3(b.x), b.y1, b.x1, b.y1)
    if side == "w":
        return Segment(r3(b.x), r3(b.y), r3(b.x), b.y1)
    return Segment(b.x1, r3(b.y), b.x1, b.y1)


def shared_edge(a: Box, b: Box) -> Segment | None:
    """Common boundary of two touching boxes, or None if they only meet at a corner."""
    if abs(a.x1 - b.x) < 1e-4 or abs(b.x1 - a.x) < 1e-4:
        x = a.x1 if abs(a.x1 - b.x) < 1e-4 else a.x
        lo, hi = max(a.y, b.y), min(a.y1, b.y1)
        if hi - lo > 1e-4:
            return Segment(r3(x), r3(lo), r3(x), r3(hi))
    if abs(a.y1 - b.y) < 1e-4 or abs(b.y1 - a.y) < 1e-4:
        y = a.y1 if abs(a.y1 - b.y) < 1e-4 else a.y
        lo, hi = max(a.x, b.x), min(a.x1, b.x1)
        if hi - lo > 1e-4:
            return Segment(r3(lo), r3(y), r3(hi), r3(y))
    return None


def side_of(b: Box, seg: Segment) -> str:
    """Which side of ``b`` the segment lies on."""
    if seg.horizontal:
        return "s" if abs(seg.offset - b.y) < 1e-4 else "n"
    return "w" if abs(seg.offset - b.x) < 1e-4 else "e"


def merge_intervals(intervals: list[tuple[float, float]], tol: float = 1e-4) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for lo, hi in sorted(intervals):
        if out and lo <= out[-1][1] + tol:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def subtract_intervals(base: tuple[float, float], holes: list[tuple[float, float]], min_len: float = 1e-3) -> list[tuple[float, float]]:
    pieces = [base]
    for hlo, hhi in holes:
        nxt: list[tuple[float, float]] = []
        for lo, hi in pieces:
            if hhi <= lo or hlo >= hi:
                nxt.append((lo, hi))
                continue
            if hlo - lo > min_len:
                nxt.append((lo, hlo))
            if hi - hhi > min_len:
                nxt.append((hhi, hi))
        pieces = nxt
    return pieces
