"""Voice mode for Add medicine: read one spoken sentence into the medicine form's fields.

The family speaks with Wispr Flow into a text box, e.g.
  "One tablet at 9 am and one tablet at 8 pm after food, the remaining quantity is 10.
   Pricing is 10 tablets for ₹55."
and this returns the schedule text, reminder times, tablets left and pricing.

Gemini reads it when GEMINI_API_KEY is set. Simple rules read it otherwise, or when Gemini fails,
so the feature still works offline. Every value is checked before it reaches the form; anything
that can't be read is left empty for the family to fill in.
"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.core.config import settings
from app.services import understanding

MAX_TEXT_LENGTH = 2000
CENT = Decimal("0.01")

FIELDS = ("instructions_text", "reminder_times", "quantity_remaining", "unit_price", "total_medicine_count")

GEMINI_PROMPT = """You fill in a medicine form for an Indian family caring for an elderly parent.
Read what the family member said and return JSON with exactly these keys:
- "instructions_text": a short schedule in plain English, e.g. "1 tablet at 9:00 AM and 8:00 PM, after food"
  (dose, times in 12-hour format, and before/after/with food if said). null if no schedule was said.
- "reminder_times": list of reminder times in 24-hour "HH:MM", in the order said, e.g. ["09:00", "20:00"]. [] if none.
- "quantity_remaining": whole number of tablets the family has left now, or null.
- "total_medicine_count": whole number of tablets in the pack or purchase the price is for, or null.
- "unit_price": price of ONE tablet in rupees as a number (pack price divided by tablets in the pack), or null.
Use only what was said. Do not guess missing values.

What they said:
\"\"\"{text}\"\"\"
"""

# ---------------------------------------------------------------- cleaning (shared by both readers)


def _clean_time(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


def _clean_times(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for v in value:
        t = _clean_time(v)
        if t and t not in out:
            out.append(t)
    return out


def _clean_count(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite() or d < 0 or d != d.to_integral_value():
        return None
    return int(d)


def _clean_price(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite() or d < 0:
        return None
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value[:500] or None


def _clean(raw: dict, source: str) -> dict:
    return {
        "instructions_text": _clean_text(raw.get("instructions_text")),
        "reminder_times": _clean_times(raw.get("reminder_times")),
        "quantity_remaining": _clean_count(raw.get("quantity_remaining")),
        "unit_price": _clean_price(raw.get("unit_price")),
        "total_medicine_count": _clean_count(raw.get("total_medicine_count")),
        "source": source,
    }


# ---------------------------------------------------------------- rules

_WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "hundred": 100,
}
_UNIT = r"(?:tablets?|tabs?|capsules?|caps?|pills?)"
_RUPEES = r"(?:rs\.?|rupees?|inr)"
_NUM = r"(\d+(?:\.\d+)?)"


def _normalise(text: str) -> str:
    t = text.lower().replace("₹", " rs ").replace("½", " half ")
    t = re.sub(r"\b(" + "|".join(_WORD_NUMBERS) + r")\b", lambda m: str(_WORD_NUMBERS[m.group(1)]), t)
    return " ".join(t.split())


def _find_times(t: str) -> list[tuple[int, int, str]]:
    """(start, end, "HH:MM") for each spoken time, in order."""
    found: list[tuple[int, int, str]] = []
    for m in re.finditer(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?\s?m|p\.?\s?m)\b\.?", t):
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if not 1 <= h <= 12 or mi > 59:
            continue
        pm = m.group(3).startswith("p")
        found.append((m.start(), m.end(), f"{(h % 12) + (12 if pm else 0):02d}:{mi:02d}"))
    for m in re.finditer(
        r"\bat (\d{1,2})(?:[:.](\d{2}))?\s*(?:o'?clock\s*)?(?:in the )?(morning|afternoon|evening|night)\b", t
    ):
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if not 1 <= h <= 12 or mi > 59 or any(s <= m.start(1) < e for s, e, _ in found):
            continue
        pm = m.group(3) != "morning" and not (m.group(3) == "night" and h == 12)
        found.append((m.start(1), m.end(), f"{(h % 12) + (12 if pm else 0):02d}:{mi:02d}"))
    found.sort()
    return found


def _dose_in(segment: str) -> str | None:
    m = re.search(r"\b(half|\d+(?:\.\d+)?)\s*(?:a\s+)?(tablet|tab|capsule|cap|pill)s?\b", segment)
    if not m:
        return None
    unit = {"tab": "tablet", "cap": "capsule"}.get(m.group(2), m.group(2))
    if m.group(1) == "half" or m.group(1) in ("0.5", ".5"):
        return f"half {unit}"
    n = Decimal(m.group(1))
    n_text = str(int(n)) if n == n.to_integral_value() else str(n)
    return f"{n_text} {unit}{'' if n == 1 else 's'}"


def _say_time(hhmm: str) -> str:
    h, mi = int(hhmm[:2]), hhmm[3:]
    return f"{h % 12 or 12}:{mi} {'PM' if h >= 12 else 'AM'}"


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _food(t: str) -> str | None:
    if re.search(r"\b(before (food|meals?|breakfast|lunch|dinner)|empty stomach)\b", t):
        return "before food"
    if re.search(r"\bafter (food|meals?|breakfast|lunch|dinner|eating)\b", t):
        return "after food"
    if re.search(r"\bwith (food|meals?|milk)\b", t):
        return "with food"
    return None


def _schedule(t: str) -> tuple[str | None, list[str]]:
    times = _find_times(t)
    food = _food(t)
    if not times:
        dose = _dose_in(t)
        text = ", ".join(x for x in (dose, food) if x) or None
        return text, []
    doses: list[str] = []
    prev_end, last = 0, None
    for start, end, _ in times:
        last = _dose_in(t[prev_end:start]) or last
        doses.append(last or "")
        prev_end = end
    first_known = next((d for d in doses if d), "1 tablet")
    doses = [d or first_known for d in doses]
    hhmm: list[str] = []
    pairs: list[tuple[str, str]] = []
    for (_, _, tm), d in zip(times, doses):
        if tm not in hhmm:
            hhmm.append(tm)
            pairs.append((d, tm))
    if len({d for d, _ in pairs}) == 1:
        text = f"{pairs[0][0]} at {_join([_say_time(tm) for _, tm in pairs])}"
    else:
        text = _join([f"{d} at {_say_time(tm)}" for d, tm in pairs])
    if food:
        text += f", {food}"
    return text, hhmm


def _quantity(t: str) -> int | None:
    patterns = [
        r"\b(?:remaining|left|balance)\s*(?:quantity|stock|count)?\s*(?:is|are|of|=|:)?\s*(\d+)\b",
        r"\b(?:quantity|stock)\s*(?:remaining|left)?\s*(?:is|are|of|=|:)?\s*(\d+)\b",
        rf"\b(\d+)\s*{_UNIT}?\s*(?:are\s+|is\s+)?(?:left|remaining)\b",
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            return int(m.group(1))
    return None


def _pricing(t: str) -> tuple[Decimal | None, int | None]:
    count: int | None = None
    unit: Decimal | None = None
    pack = re.search(
        rf"\b(\d+)\s*{_UNIT}\s*(?:for|costs?|=)\s*(?:of\s*)?{_RUPEES}?\s*{_NUM}", t
    )
    if pack and int(pack.group(1)) > 0:
        count = int(pack.group(1))
        unit = Decimal(pack.group(2)) / count
    else:
        per = re.search(rf"\b{_RUPEES}\s*{_NUM}\s*(?:per|each|a|/|for 1)\b", t) or re.search(
            rf"\b{_NUM}\s*{_RUPEES}\s*(?:per|each|a|/|for 1)\b", t
        )
        if per:
            unit = Decimal(per.group(1))
        total = re.search(rf"\btotal\s*(?:of\s*)?(\d+)\s*{_UNIT}", t)
        if total:
            count = int(total.group(1))
    return (unit.quantize(CENT, rounding=ROUND_HALF_UP) if unit is not None else None), count


def _by_rules(text: str) -> dict:
    t = _normalise(text)
    instructions, times = _schedule(t)
    unit, count = _pricing(t)
    return _clean(
        {
            "instructions_text": instructions,
            "reminder_times": times,
            "quantity_remaining": _quantity(t),
            "unit_price": unit,
            "total_medicine_count": count,
        },
        "rules",
    )


# ---------------------------------------------------------------- entry point


def parse_medicine_text(text: str) -> dict:
    """Read a spoken medicine description into form fields. Raises ValueError for empty text."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Say or type the schedule, quantity and price first.")
    text = text[:MAX_TEXT_LENGTH]
    if settings.gemini_api_key:
        try:
            raw = understanding.ask_gemini(GEMINI_PROMPT.format(text=text))
            if isinstance(raw, dict):
                return _clean(raw, "gemini")
        except Exception:  # noqa: BLE001 - any Gemini trouble falls back to the rules
            pass
    return _by_rules(text)
