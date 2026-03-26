from __future__ import annotations

import re
from collections import defaultdict

from app.models.schemas import Preferences, RoomRequest, StructuredBrief

SQFT_TO_SQM = 0.0929

ROOM_ALIASES = {
    "studio": ["studio"],
    "bedroom": ["bedroom", "bedrooms", "bed", "beds"],
    "bathroom": ["bathroom", "bathrooms", "bath", "baths", "wc", "restroom"],
    "kitchen": ["kitchen"],
    "living": ["living", "lounge", "family room"],
    "dining": ["dining", "dining room"],
    "entry": ["entry", "foyer", "lobby"],
    "corridor": ["hallway", "corridor", "hall"],
    "garage": ["garage"],
    "laundry": ["laundry"],
    "storage": ["storage", "store"],
    "reception": ["reception"],
    "meeting_room": ["meeting room", "conference"],
    "private_office": ["private office", "office"],
    "open_office": ["open office"],
    "break_room": ["break room", "pantry"],
    "server_room": ["server room"],
    "stair": ["stair", "stairs", "stairwell"],
    "ensuite": ["ensuite", "en-suite"],
}


def _count_alias(text: str, aliases: list[str]) -> int:
    found = 0
    for a in aliases:
        # Handles forms like "3 bedrooms" or standalone room mention.
        num_match = re.findall(rf"(\d+)\s+{re.escape(a)}s?\b", text)
        if num_match:
            found = max(found, max(int(n) for n in num_match))
        elif re.search(rf"\b{re.escape(a)}s?\b", text):
            found = max(found, 1)
    return found


def _extract_area_sqft(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft|square\s*feet|sf)", text)
    if m:
        return float(m.group(1))
    return None


def _infer_area_sqm(counts: dict[str, int]) -> float:
    # Heuristic defaults when area is absent.
    sqm = 0.0
    if counts.get("studio", 0) > 0:
        sqm += 40.0
    sqm += counts.get("bedroom", 0) * 15.0
    sqm += counts.get("bathroom", 0) * 5.0
    if counts.get("kitchen", 0) > 0:
        sqm += 10.0
    if counts.get("living", 0) > 0:
        sqm += 15.0
    if sqm <= 0:
        sqm = 85.0
    return sqm


def _detect_building_type(text: str) -> str:
    commercial_tokens = ["office", "reception", "meeting", "commercial", "lobby", "workstation"]
    residential_tokens = ["bedroom", "house", "apartment", "studio", "bathroom", "living"]
    has_com = any(t in text for t in commercial_tokens)
    has_res = any(t in text for t in residential_tokens)
    if has_com and has_res:
        return "mixed"
    if has_com:
        return "commercial"
    return "residential"


def _detect_story_count(text: str) -> int:
    if "two story" in text or "two-storey" in text or "2 story" in text:
        return 2
    if "three story" in text or "3 story" in text:
        return 3
    m = re.search(r"(\d+)\s*story", text)
    if m:
        return max(1, int(m.group(1)))
    return 1


def _detect_style(text: str, area_sqm: float) -> str:
    if "traditional" in text:
        return "traditional"
    if "open plan" in text or "open-plan" in text:
        return "open_plan"
    return "open_plan" if area_sqm < 80 else "traditional"


def _extract_explicit_adjacency(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for a in ["kitchen", "dining", "living", "entry", "bathroom", "bedroom", "reception", "meeting_room", "private_office"]:
        for b in ["kitchen", "dining", "living", "entry", "bathroom", "bedroom", "reception", "meeting_room", "private_office"]:
            if a == b:
                continue
            if f"{a} near {b}" in text or f"{a} adjacent {b}" in text:
                pairs.append((a, b))
    return pairs


def _normalize_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for room, aliases in ROOM_ALIASES.items():
        counts[room] = _count_alias(text, aliases)

    # Common shorthand: "3 bed 2 bath".
    m_bed = re.search(r"(\d+)\s*bed\b", text)
    if m_bed:
        counts["bedroom"] = max(counts["bedroom"], int(m_bed.group(1)))
    m_bath = re.search(r"(\d+(?:\.\d+)?)\s*bath\b", text)
    if m_bath:
        counts["bathroom"] = max(counts["bathroom"], max(1, int(float(m_bath.group(1)))))

    btype = _detect_building_type(text)
    if btype == "residential":
        if counts["bedroom"] == 0 and counts["studio"] == 0:
            counts["bedroom"] = 1
        if counts["studio"] == 0:
            counts["living"] = max(1, counts["living"])
        counts["kitchen"] = max(1, counts["kitchen"])
        counts["bathroom"] = max(1, counts["bathroom"])
        counts["entry"] = max(1, counts["entry"])
        counts["corridor"] = max(1, counts["corridor"])
    else:
        counts["reception"] = max(1, counts["reception"])
        counts["corridor"] = max(1, counts["corridor"])
        counts["bathroom"] = max(1, counts["bathroom"])
        if counts["private_office"] == 0 and counts["open_office"] == 0:
            counts["open_office"] = 1
    return counts


def _to_room_requests(counts: dict[str, int], stories: int) -> list[RoomRequest]:
    rooms: list[RoomRequest] = []
    for rtype, cnt in counts.items():
        if cnt <= 0:
            continue
        if rtype == "studio":
            rooms.append(RoomRequest(type="living", count=1))
            continue
        rooms.append(RoomRequest(type=rtype, count=cnt))
    if stories > 1 and not any(r.type == "stair" for r in rooms):
        rooms.append(RoomRequest(type="stair", count=1))
    return rooms


def interpret_brief(prompt: str) -> StructuredBrief:
    text = prompt.lower().strip()
    counts = _normalize_counts(text)

    area_sqft = _extract_area_sqft(text)
    if area_sqft is None:
        area_sqm = _infer_area_sqm(counts)
        area_sqft = area_sqm / SQFT_TO_SQM
    else:
        area_sqm = area_sqft * SQFT_TO_SQM

    building_type = _detect_building_type(text)
    story_count = _detect_story_count(text)
    style = _detect_style(text, area_sqm)

    prefs = Preferences(
        open_kitchen=("open kitchen" in text or "open plan" in text or "open-plan" in text),
        privacy=("privacy" in text or "private" in text),
        compact=("compact" in text or "efficient" in text or area_sqm < 65),
        daylight=("daylight" in text or "bright" in text or "sun" in text),
        efficient_circulation=True,
    )

    return StructuredBrief(
        raw_prompt=prompt,
        target_area_sqft=round(area_sqft, 2),
        target_area_sqm=round(area_sqm, 2),
        rooms=_to_room_requests(counts, story_count),
        preferences=prefs,
        building_type=building_type,  # type: ignore[arg-type]
        story_count=story_count,
        style_preference=style,  # type: ignore[arg-type]
        explicit_adjacency=_extract_explicit_adjacency(text),
    )
