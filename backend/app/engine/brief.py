"""Natural-language brief interpreter.

Turns a sentence such as "3 bed 2.5 bath house, 1,600 sq ft, open plan" into
a :class:`StructuredBrief`. The parser is rule based and deterministic; every
assumption it makes is recorded in ``notes`` so the UI can show the user what
was understood.
"""

from __future__ import annotations

import re

from app.engine.rooms import SPECS
from app.models.schemas import Preferences, RoomRequest, StructuredBrief

SQFT_PER_SQM = 10.7639

NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "single": 1,
    "two": 2,
    "double": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_NUM = r"(\d+(?:\.\d+)?|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"

# Patterns are matched against the normalised prompt. Order matters only for
# readability; each room type is counted independently.
ROOM_PATTERNS: dict[str, str] = {
    "bedroom": r"bed(?:room)?s?|br|bd|bdrm?s?",
    "bathroom": r"bath(?:room)?s?|ba|restrooms?|washrooms?|wcs?|toilets?",
    "living": r"living(?:\s+rooms?)?|lounges?|family\s+rooms?|sitting\s+rooms?",
    "dining": r"dining(?:\s+rooms?|\s+areas?)?",
    "kitchen": r"kitchens?",
    "study": r"stud(?:y|ies)|home\s+offices?|dens?",
    "laundry": r"laundry(?:\s+rooms?)?|utility(?:\s+rooms?)?",
    "storage": r"storage(?:\s+rooms?)?|store\s?rooms?|pantr(?:y|ies)",
    "garage": r"(?:car\s+)?garages?",
    "private_office": r"(?:private\s+)?offices?",
    "meeting_room": r"meeting\s+rooms?|conference(?:\s+rooms?)?|boardrooms?",
    "reception": r"receptions?|lobb(?:y|ies)|waiting\s+areas?",
    "open_office": r"open[\s-]+(?:plan\s+)?offices?|open\s+work\s?spaces?|bullpens?",
    "break_room": r"break\s?rooms?|kitchenettes?|staff\s+rooms?",
    "server_room": r"server\s+rooms?|it\s+rooms?|comms?\s+rooms?",
}

# A bare "office" in a commercial brief describes the building, not a room.
STANDALONE_OVERRIDES = {"private_office": r"private\s+offices?"}

RESIDENTIAL_WORDS = (
    r"\b(bed(room)?s?|br|bd|house|home|apartment|flat|condo|studio|cottage|cabin|villa|bungalow|townhouse|duplex|living room|family)\b"
)
COMMERCIAL_WORDS = r"\b(office space|commercial|startup|company|agency|clinic|workstations?|desks|employees|staff|reception|meeting rooms?|conference|coworking|co-working|private offices?|open office|retail)\b"


def _num(token: str) -> float:
    return float(token) if token[0].isdigit() else float(NUMBER_WORDS[token])


def _normalise(prompt: str) -> str:
    text = prompt.lower()
    text = text.replace("²", "2").replace("’", "'").replace("–", "-").replace("—", "-")
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # 1,200 -> 1200
    text = re.sub(r"(\d)\s*k\s*(?=sq|square|sf)", lambda m: m.group(1) + "000 ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_area(text: str) -> tuple[float | None, str | None]:
    sqft = re.search(r"(\d+(?:\.\d+)?)\s*(?:sq\.?\s*ft\.?|sqft|square\s*f(?:ee|oo)t|sf\b|ft2|feet2)", text)
    if sqft:
        return float(sqft.group(1)) / SQFT_PER_SQM, "sqft"
    sqm = re.search(r"(\d+(?:\.\d+)?)\s*(?:sq\.?\s*m\b|sqm|square\s*met(?:er|re)s?|m2\b|sq\s*met(?:er|re)s?)", text)
    if sqm:
        return float(sqm.group(1)), "sqm"
    return None, None


def _count(text: str, pattern: str, standalone: str | None = None) -> tuple[int, bool]:
    """Return (count, mentioned). Numbers directly before the noun win."""
    best = 0
    mentioned = False
    for m in re.finditer(rf"\b{_NUM}[\s-]*(?:x\s*)?(?:{pattern})\b", text):
        value = _num(m.group(1))
        best = max(best, int(value))
        mentioned = True
    if not mentioned and re.search(rf"\b(?:{standalone or pattern})\b", text):
        mentioned = True
        best = 1
    return best, mentioned


def _bathrooms(text: str) -> tuple[int, int, bool]:
    """Return (full bathrooms, powder rooms, mentioned)."""
    full = 0
    powder = 0
    mentioned = False
    for m in re.finditer(rf"\b{_NUM}[\s-]*(?:{ROOM_PATTERNS['bathroom']})\b", text):
        value = _num(m.group(1))
        mentioned = True
        whole = int(value)
        full = max(full, whole)
        if value - whole >= 0.5:
            powder = max(powder, 1)
    half = re.search(rf"(?:\b{_NUM}\s+)?(?:half[\s-]?baths?|powder\s+rooms?|guest\s+(?:wc|toilet|bath))", text)
    if half:
        powder = max(powder, int(_num(half.group(1))) if half.group(1) else 1)
    if not mentioned and re.search(rf"\b(?:{ROOM_PATTERNS['bathroom']})\b", text):
        mentioned = True
        full = max(full, 1)
    return full, powder, mentioned


def _stories(text: str) -> int:
    m = re.search(rf"\b{_NUM}[\s-]*(?:stor(?:e?y|ies|eys)|levels?|floors?)\b", text)
    if m:
        return max(1, min(3, int(_num(m.group(1)))))
    if re.search(r"\b(upstairs|downstairs|duplex|townhouse)\b", text):
        return 2
    return 1


def _workstations(text: str) -> int:
    m = re.search(r"(\d+)\s*(?:people|persons|employees|staff|desks|workstations|seats|team members)", text)
    return int(m.group(1)) if m else 0


def _detect_type(text: str) -> str:
    res = bool(re.search(RESIDENTIAL_WORDS, text))
    com = bool(re.search(COMMERCIAL_WORDS, text))
    if com and not res:
        return "commercial"
    if not res and re.search(r"\boffices?\b", text) and not re.search(r"home\s+office", text):
        return "commercial"
    return "residential"


def _estimate_area(counts: dict[str, int], workstations: int) -> float:
    total = 0.0
    for rtype, n in counts.items():
        if n <= 0 or rtype == "corridor":
            continue
        base = SPECS[rtype].base_area
        if rtype == "garage":
            total += base + 16.0 * (n - 1)
        elif rtype == "open_office" and workstations:
            total += max(base, 6.5 * workstations)
        else:
            total += base * n
    if counts.get("bedroom", 0) >= 1:
        total += 3.0  # primary bedroom is larger than the base size
    return round(total * 1.12, 1)


def interpret_brief(prompt: str) -> StructuredBrief:
    text = _normalise(prompt)
    notes: list[str] = []
    building_type = _detect_type(text)
    counts: dict[str, int] = {}
    mentioned: dict[str, bool] = {}

    for rtype, pattern in ROOM_PATTERNS.items():
        if rtype == "bathroom":
            continue
        counts[rtype], mentioned[rtype] = _count(text, pattern, STANDALONE_OVERRIDES.get(rtype))

    full, powder, bath_mentioned = _bathrooms(text)
    counts["bathroom"], mentioned["bathroom"] = full, bath_mentioned
    counts["powder"] = powder
    counts["ensuite"] = 1 if re.search(r"en[\s-]?suite|master\s+(?:suite|bath)|primary\s+(?:suite|bath)", text) else 0

    garage = re.search(rf"\b{_NUM}[\s-]*car\s+garage", text)
    if garage:
        counts["garage"] = max(1, min(3, int(_num(garage.group(1)))))
    elif re.search(r"double\s+garage", text):
        counts["garage"] = 2

    studio = bool(re.search(r"\bstudio\b", text)) and counts["bedroom"] == 0
    stories = _stories(text)

    if building_type == "residential":
        for t in ("private_office", "meeting_room", "reception", "open_office", "break_room", "server_room"):
            counts[t] = 0
        if re.search(r"\boffice\b", text) and counts["study"] == 0:
            counts["study"] = 1
        if studio:
            counts["bedroom"] = 0
            counts["living"] = 0
            counts["studio"] = 1
            notes.append("Studio: living and sleeping share one main room")
        elif counts["bedroom"] == 0:
            counts["bedroom"] = 1
            notes.append("No bedroom count given; assumed 1 bedroom")
        if not studio:
            counts["living"] = max(1, counts["living"])
        counts["kitchen"] = 1
        if counts["bathroom"] == 0:
            counts["bathroom"] = 1 if counts["bedroom"] < 3 else 2
            notes.append(f"Assumed {counts['bathroom']} bathroom{'s' if counts['bathroom'] > 1 else ''}")
        if counts["ensuite"] and counts["bedroom"] == 0:
            counts["ensuite"] = 0
        if counts["ensuite"] and counts["bathroom"] > 1 and mentioned["bathroom"]:
            # "3 bathrooms including a master ensuite" counts the ensuite once.
            counts["bathroom"] -= 1
        counts["entry"] = 1
        if counts["dining"] == 0 and not studio and (counts["bedroom"] >= 3):
            counts["dining"] = 1
            notes.append("Added a dining area for a family-sized home")
        counts["open_office"] = 0
    else:
        for t in ("bedroom", "living", "dining", "garage", "study", "ensuite", "powder", "studio"):
            counts[t] = 0
        if counts["reception"] == 0:
            counts["reception"] = 1
            notes.append("Added a reception area")
        if counts["bathroom"] == 0:
            counts["bathroom"] = 1
            notes.append("Assumed 1 restroom")
        if counts["private_office"] == 0 and counts["open_office"] == 0:
            counts["open_office"] = 1
            notes.append("No offices listed; added an open office")
        if counts["kitchen"] and counts["break_room"] == 0:
            counts["break_room"] = 1
        counts["kitchen"] = 0
        counts["laundry"] = 0

    workstations = _workstations(text)
    area, unit = _extract_area(text)
    if area is None:
        area = _estimate_area(counts, workstations)
        area_source = "estimated"
        notes.append(f"Area not stated; estimated {area:.0f} m² ({area * SQFT_PER_SQM:,.0f} ft²) from the program")
    else:
        area_source = "stated"
    area = max(18.0, min(1500.0, area))

    if stories > 1:
        notes.append(f"{stories} levels connected by a stair")
        if building_type == "residential" and counts["powder"] == 0 and counts["bathroom"] < counts["bedroom"] + 1:
            counts["powder"] = 1
            notes.append("Added a powder room on the entry level")

    if re.search(r"\btraditional\b|closed kitchen|separate kitchen|formal dining", text):
        style = "traditional"
    else:
        style = "open_plan"

    prefs = Preferences(
        daylight=bool(re.search(r"daylight|natural light|bright|sunny|light[\s-]filled|lots of light", text)),
        privacy=bool(re.search(r"privacy|private(?!\s+offices?)|secluded|quiet", text)),
        compact=bool(re.search(r"compact|efficient|small|tiny|minimal", text)),
    )

    order = list(SPECS)
    rooms = [RoomRequest(type=t, count=min(12, counts[t])) for t in order if counts.get(t, 0) > 0]  # type: ignore[arg-type]
    return StructuredBrief(
        raw_prompt=prompt.strip()[:2000],
        building_type=building_type,  # type: ignore[arg-type]
        target_area_sqm=round(area, 2),
        area_source=area_source,  # type: ignore[arg-type]
        stories=stories,
        style=style,  # type: ignore[arg-type]
        rooms=rooms,
        preferences=prefs,
        notes=notes,
    )
