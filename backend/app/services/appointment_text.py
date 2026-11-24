"""Voice mode for Add appointment: read one spoken sentence into the appointment form.

The family speaks with Wispr Flow into a text box, e.g.
  "Amma's eye check-up with Dr. Rao at Apollo Hospital next Tuesday at 10:30 am. Bring the old reports."
and this returns who it is for, the reason, doctor, place, date, time and notes.

Gemini reads it when GEMINI_API_KEY is set; simple rules read it otherwise, or when Gemini fails.
The parent is matched only against the family's own care profiles.
"""

import difflib
import re
from datetime import date, timedelta
from typing import Any

from app.core.config import settings
from app.services import understanding
from app.services.task_text import read_due_date

MAX_TEXT_LENGTH = 2000

Profile = tuple[str, str, str]  # (care profile id, display name, greeting name)

GEMINI_PROMPT = """You fill in a doctor's appointment form for a family caring for an elderly parent in India.
Today is {weekday}, {today}. The family's parents: {names}.

Read what they said and return JSON with exactly these keys:
- "for_whom": which parent it is for, using a name from the list above (they may say amma / appa / mom / dad), or null.
- "reason": a short reason, e.g. "Eye check-up", "Blood test", "Cardiology follow-up". null if not said.
- "provider": the doctor or clinic, e.g. "Dr. Rao", or null.
- "location": the hospital / clinic / place, e.g. "Apollo Hospital, Jayanagar", or null.
- "date": "YYYY-MM-DD" worked out from today ("next Tuesday" = the coming Tuesday), or null.
- "time": 24-hour "HH:MM", or null.
- "notes": anything else worth remembering (what to bring, fasting, transport), or null.
Use only what was said.

What they said:
\"\"\"{text}\"\"\"
"""

_KIN = [
    {"amma", "mom", "mother", "mummy", "mommy", "maa", "ma", "aai", "amme"},
    {"appa", "dad", "father", "daddy", "papa", "pappa", "pa", "baba", "achan"},
    {"paati", "grandma", "grandmother", "nani", "dadi", "ajji", "ammamma"},
    {"thatha", "grandpa", "grandfather", "nana", "dada", "ajja"},
]
_IGNORE_NAME_WORDS = {"demo", "parent", "mr", "mrs", "ms", "dr"}

# ---------------------------------------------------------------- parent


def _name_words(profile: Profile) -> set[str]:
    words = set()
    for part in (profile[1], profile[2]):
        for w in re.findall(r"[a-z]+", (part or "").lower()):
            if len(w) >= 2 and w not in _IGNORE_NAME_WORDS:
                words.add(w)
    return words


def _word_matches(spoken: str, name_word: str) -> bool:
    if spoken == name_word:
        return True
    for group in _KIN:
        if spoken in group and name_word in group:
            return True
    return len(spoken) >= 4 and difflib.SequenceMatcher(None, spoken, name_word).ratio() >= 0.85


def match_profile(text: str | None, profiles: list[Profile]) -> Profile | None:
    """The parent a sentence (or a spoken name) is about; the only parent when the family has one."""
    if text and isinstance(text, str):
        tokens = [re.sub(r"'s$", "", t) for t in re.findall(r"[a-z']+", text.lower())]
        hits = [p for p in profiles if any(_word_matches(t, w) for t in tokens for w in _name_words(p))]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return None
    return profiles[0] if len(profiles) == 1 else None


# ---------------------------------------------------------------- time

_TIME_RE = re.compile(
    r"(?:\bat\s+)?\b\d{1,2}(?:[:.]\d{2})?\s*(?:a\.?\s?m\b\.?|p\.?\s?m\b\.?)"
    r"|(?:\bat\s+)?\b\d{1,2}(?:[:.]\d{2})?\s*(?:o'?clock\s*)?(?:in the\s+)?(?:morning|afternoon|evening|night)\b"
    r"|(?:\bat\s+)?\b(?:noon|midday)\b",
    re.IGNORECASE,
)


def read_time(text: str) -> str | None:
    t = text.lower()
    m = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?\s?m|p\.?\s?m)\b", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if 1 <= h <= 12 and mi <= 59:
            return f"{(h % 12) + (12 if m.group(3).startswith('p') else 0):02d}:{mi:02d}"
    m = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(?:o'?clock\s*)?(?:in the\s+)?(morning|afternoon|evening|night)\b", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if 1 <= h <= 12 and mi <= 59:
            pm = m.group(3) != "morning" and not (m.group(3) == "night" and h == 12)
            return f"{(h % 12) + (12 if pm else 0):02d}:{mi:02d}"
    if re.search(r"\b(noon|midday)\b", t):
        return "12:00"
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)  # "14:30"
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


# ---------------------------------------------------------------- doctor, place, reason

_STOP = {
    "at", "on", "in", "for", "with", "by", "to", "and", "next", "this", "coming", "tomorrow", "today", "tonight",
    "day", "the", "a", "an", "around", "about", "before", "after", "from", "is", "please",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "morning", "evening",
    "afternoon", "night", "noon", "week", "month",
}
_MONTHS = {"jan", "january", "feb", "february", "mar", "march", "apr", "april", "may", "jun", "june", "jul",
           "july", "aug", "august", "sep", "sept", "september", "oct", "october", "nov", "november", "dec",
           "december"}


def _titled(words: list[str]) -> str:
    return " ".join(w if any(c.isupper() for c in w) else w.capitalize() for w in words)


def read_provider(text: str) -> str | None:
    m = re.search(r"\b(?:dr\.?|doctor)\s+([A-Za-z][A-Za-z'-]+)(?:\s+([A-Za-z][A-Za-z'-]+))?", text, re.IGNORECASE)
    if not m or m.group(1).lower() in _STOP:
        return None
    words = [m.group(1)]
    if m.group(2) and m.group(2).lower() not in _STOP and m.group(2).lower() not in _MONTHS:
        words.append(m.group(2))
    return "Dr. " + _titled(words)


def read_location(text: str) -> str | None:
    for m in re.finditer(r"\bat\s+", text, re.IGNORECASE):
        rest = text[m.end():]
        tokens = re.findall(r"[^\s]+", rest)
        kept: list[str] = []
        for tok in tokens:
            bare = tok.strip(",.;:!?").lower()
            if not bare or bare in _STOP or bare in _MONTHS or re.match(r"^\d", bare) or bare in ("am", "pm"):
                break
            if kept == [] and bare in ("dr", "doctor"):
                break
            kept.append(tok.rstrip(".;:!?"))
            if tok.endswith((".", ";", "!", "?")) or (tok.endswith(",") and len(kept) > 4):
                break
        place = " ".join(kept).strip(" ,")
        if place:
            return _titled(place.split(" "))[:255]
    return None


_REASON_WORDS = (
    r"check[\s-]?up|follow[\s-]?up|review|tests?|scan|x[\s-]?ray|mri|ct|consultation|vaccination|vaccine|"
    r"therapy|physiotherapy|dialysis|ecg|echo|surgery|operation|dressing|injection|screening|counselling"
)
_SPECIALISTS = (
    r"dentist|cardiologist|neurologist|ophthalmologist|eye doctor|dermatologist|orthopaedic|orthopedic|"
    r"physio|ent|gynaecologist|gynecologist|psychiatrist|diabetologist|nephrologist|urologist|pulmonologist|"
    r"oncologist|gastroenterologist|geriatrician"
)
_NOT_REASON = {"the", "a", "an", "for", "to", "take", "his", "her", "my", "our", "see", "book", "have", "has",
               "get", "with", "and", "on", "at", "is", "regular", "her's", "their", "go"}


def read_reason(text: str, profiles: list[Profile], provider: str | None) -> str | None:
    names = set().union(*(_name_words(p) for p in profiles)) if profiles else set()
    m = re.search(r"((?:[A-Za-z][\w'-]*\s+){0,2})\b(" + _REASON_WORDS + r")\b", text, re.IGNORECASE)
    if m:
        before = [w for w in m.group(1).split() if w]
        keep: list[str] = []
        for w in reversed(before):
            bare = re.sub(r"'s$", "", w.lower())
            if bare in _NOT_REASON or bare in names or any(bare in g for g in _KIN) or w.endswith("'s"):
                break
            keep.insert(0, w)
        reason = " ".join(keep + [m.group(2)])
        return reason[:1].upper() + reason[1:]
    m = re.search(r"\b(" + _SPECIALISTS + r")\b", text, re.IGNORECASE)
    if m:
        word = m.group(1)
        word = word.upper() if word.lower() == "ent" else word.lower()
        return f"{word[:1].upper()}{word[1:]} visit"
    if provider:
        return "Doctor visit"
    return None


def _sentences(text: str) -> list[str]:
    """Split into sentences without breaking at "Dr." / "Mr." / "St."."""
    guarded = re.sub(r"\b(dr|mr|mrs|ms|st|no)\.", lambda m: m.group(1) + "§", text, flags=re.IGNORECASE)
    parts = re.split(r"(?<=[.!?])\s+|\n+", guarded)
    return [p.replace("§", ".").strip() for p in parts if p.strip()]


def read_notes(text: str) -> str | None:
    sentences = _sentences(text)
    notes = [s if s.endswith((".", "!", "?")) else s + "." for s in sentences[1:] if len(s.split()) >= 3]
    # "…, bring the old reports" in the same sentence
    if sentences:
        m = re.search(r"[,;]\s*((?:please\s+)?(?:bring|carry|take|fasting|come|don'?t|do not|remember)\b[^.]*)",
                      sentences[0], re.IGNORECASE)
        if m:
            clause = m.group(1).strip()
            notes.insert(0, clause[:1].upper() + clause[1:] + ".")
    return " ".join(notes)[:2000] or None


# ---------------------------------------------------------------- rules / Gemini


def _result(profile: Profile | None, reason, provider, location, when, time, notes, source) -> dict:
    return {
        "care_recipient_id": profile[0] if profile else None,
        "care_recipient_name": profile[1] if profile else None,
        "reason": reason,
        "provider": provider,
        "location": location,
        "scheduled_date": when,
        "start_time": time,
        "notes": notes,
        "source": source,
    }


def _by_rules(text: str, today: date, profiles: list[Profile]) -> dict:
    when = read_due_date(text, today)
    provider = read_provider(text)
    return _result(
        match_profile(text, profiles),
        read_reason(text, profiles, provider),
        provider,
        read_location(_TIME_RE.sub(" ", text)),
        when.isoformat() if when else None,
        read_time(text),
        read_notes(text),
        "rules",
    )


def _text(value: Any, limit: int = 255) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value[:limit] or None


def _clean_gemini(raw: dict, today: date, profiles: list[Profile]) -> dict | None:
    reason = _text(raw.get("reason"))
    when = None
    if isinstance(raw.get("date"), str):
        try:
            d = date.fromisoformat(raw["date"].strip())
            if today - timedelta(days=1) <= d <= today + timedelta(days=3 * 366):
                when = d.isoformat()
        except ValueError:
            when = None
    if reason is None and when is None:
        return None
    time = None
    if isinstance(raw.get("time"), str):
        m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", raw["time"])
        if m and int(m.group(1)) <= 23 and int(m.group(2)) <= 59:
            time = f"{int(m.group(1)):02d}:{m.group(2)}"
    who = raw.get("for_whom")
    profile = match_profile(who, profiles) if isinstance(who, str) and who.strip() else (
        profiles[0] if len(profiles) == 1 else None)
    return _result(
        profile,
        reason[:1].upper() + reason[1:] if reason else None,
        _text(raw.get("provider")),
        _text(raw.get("location")),
        when,
        time,
        _text(raw.get("notes"), 2000),
        "gemini",
    )


def parse_appointment_text(text: str, today: date, profiles: list[Profile]) -> dict:
    """Read a spoken appointment into form fields. Raises ValueError for empty text."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Say or type the appointment first.")
    text = text[:MAX_TEXT_LENGTH]
    if settings.gemini_api_key:
        names = ", ".join(f"{p[1]} (called {p[2]})" if p[2] and p[2] != p[1] else p[1] for p in profiles)
        prompt = GEMINI_PROMPT.format(
            weekday=today.strftime("%A"), today=today.isoformat(), names=names or "none", text=text
        )
        try:
            raw = understanding.ask_gemini(prompt)
            if isinstance(raw, dict):
                cleaned = _clean_gemini(raw, today, profiles)
                if cleaned is not None:
                    return cleaned
        except Exception:  # noqa: BLE001 - any Gemini trouble falls back to the rules
            pass
    return _by_rules(text, today, profiles)
