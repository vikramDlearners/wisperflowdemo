"""Voice mode for New task: read one spoken sentence into the task form.

The family speaks with Wispr Flow into a text box, e.g.
  "Get the medicine from the store next week and assign it to Deepak"
and this returns the title, notes, due date, urgency and the family member to assign it to.

Gemini reads it when GEMINI_API_KEY is set; simple rules read it otherwise, or when Gemini fails.
The person is always matched against the family's own members (forgiving small spelling slips, so
"deepek" finds Deepak). Nobody outside the family is ever returned.
"""

import calendar
import difflib
import re
from datetime import date, timedelta
from typing import Any

from app.core.config import settings
from app.services import understanding

MAX_TEXT_LENGTH = 2000
NAME_MATCH = 0.75
PRIORITIES = ("low", "normal", "high")

Member = tuple[str, str]  # (user_id, display name)

GEMINI_PROMPT = """You fill in a task form for a family that shares the care of an elderly parent.
Today is {weekday}, {today}. Family members: {names}. The person speaking is {me}.

Read what they said and return JSON with exactly these keys:
- "title": a short task title (a few words, starting with a verb), without the date or who does it.
- "description": extra details worth keeping as notes, or null.
- "due_date": the due date as "YYYY-MM-DD" worked out from today ("next week" = 7 days from today), or null.
- "priority": "high" if they said urgent / important / asap, "low" if no rush, else "normal".
- "assignee_name": the family member's name exactly as listed above if they said who should do it
  ("me" means {me}), else null.
Use only what was said.

What they said:
\"\"\"{text}\"\"\"
"""

# ---------------------------------------------------------------- people


def match_member(spoken: str | None, members: list[Member], me_id: str | None) -> Member | None:
    """The family member a spoken name refers to, or None. "me" is the speaker."""
    if not spoken or not isinstance(spoken, str):
        return None
    s = " ".join(spoken.lower().split()).strip(" .,:;!?'\"")
    if not s:
        return None
    if s in ("me", "myself", "i", "mine"):
        return next((m for m in members if m[0] == me_id), None)
    best: list[tuple[float, Member]] = []
    for member in members:
        full = member[1].lower().strip()
        first = full.split()[0] if full else ""
        score = max(
            difflib.SequenceMatcher(None, s, full).ratio(),
            difflib.SequenceMatcher(None, s, first).ratio(),
            difflib.SequenceMatcher(None, s.split()[0], first).ratio() if s.split() else 0.0,
        )
        best.append((score, member))
    best.sort(key=lambda x: -x[0])
    if not best or best[0][0] < NAME_MATCH:
        return None
    if len(best) > 1 and best[1][0] == best[0][0]:
        return None  # two people match equally well: let the family choose
    return best[0][1]


# ---------------------------------------------------------------- dates

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                 "eight": 8, "nine": 9, "ten": 10}
_MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_LEAD = r"(?:\b(?:by|on|before|for|due|until|till|this|coming|the)\s+)*"

# Phrases that set the due date; each is removed from the title.
_DATE_PATTERNS = [
    r"\bday after tomorrow\b",
    r"\b(?:today|tonight|this evening|this afternoon|this morning)\b",
    r"\btomorrow(?: morning| evening| night)?\b",
    r"\bin (?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten) (?:day|week|month)s?\b",
    r"\bnext (?:week|month)\b",
    r"\b(?:this )?weekend\b",
    r"\bend of (?:the |this )?(?:week|month)\b",
    r"\b(?:next |this |coming )?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b\d{1,2}(?:st|nd|rd|th)?(?: of)? " + _MONTH_RE,
    r"\b" + _MONTH_RE + r" \d{1,2}(?:st|nd|rd|th)?\b",
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
]
_DATE_RE = re.compile(_LEAD + r"(?:" + "|".join(_DATE_PATTERNS) + r")", re.IGNORECASE)


def _add_months(d: date, n: int) -> date:
    month = d.month - 1 + n
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _next_weekday(today: date, weekday: int) -> date:
    ahead = (weekday - today.weekday()) % 7
    return today + timedelta(days=ahead or 7)


def _calendar_date(today: date, day: int, month: int, year: int | None = None) -> date | None:
    try:
        d = date(year or today.year, month, day)
    except ValueError:
        return None
    if year is None and d < today:
        d = date(today.year + 1, month, day) if day <= calendar.monthrange(today.year + 1, month)[1] else None
    return d


def read_due_date(text: str, today: date) -> date | None:
    t = text.lower()
    if re.search(r"\bday after tomorrow\b", t):
        return today + timedelta(days=2)
    if re.search(r"\b(today|tonight|this evening|this afternoon|this morning)\b", t):
        return today
    if re.search(r"\btomorrow\b", t):
        return today + timedelta(days=1)
    m = re.search(r"\bin (\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten) (day|week|month)s?\b", t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _NUMBER_WORDS[m.group(1)]
        if m.group(2) == "month":
            return _add_months(today, n)
        return today + timedelta(days=n * (7 if m.group(2) == "week" else 1))
    if re.search(r"\bnext week\b", t):
        return today + timedelta(days=7)
    if re.search(r"\bnext month\b", t):
        return _add_months(today, 1)
    if re.search(r"\bweekend\b", t):
        return today if today.weekday() == 5 else _next_weekday(today, 5)
    m = re.search(r"\bend of (?:the |this )?(week|month)\b", t)
    if m:
        if m.group(1) == "month":
            return date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
        return today if today.weekday() == 4 else _next_weekday(today, 4)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?(?: of)? " + _MONTH_RE, t)
    if m:
        return _calendar_date(today, int(m.group(1)), _MONTHS.index(m.group(2)) + 1)
    m = re.search(r"\b" + _MONTH_RE + r" (\d{1,2})(?:st|nd|rd|th)?\b", t)
    if m:
        return _calendar_date(today, int(m.group(2)), _MONTHS.index(m.group(1)) + 1)
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)  # Indian order: day/month
    if m:
        year = int(m.group(3)) if m.group(3) else None
        if year is not None and year < 100:
            year += 2000
        return _calendar_date(today, int(m.group(1)), int(m.group(2)), year)
    m = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", t)
    if m:
        return _next_weekday(today, _WEEKDAYS.index(m.group(1)))
    return None


# ---------------------------------------------------------------- rules

_NAME = r"([a-z][a-z.'-]*)(?:\s+([a-z][a-z.'-]*))?"
_ASSIGN_RE = re.compile(
    r"[,;]?\s*(?:\band\s+)?(?:please\s+)?\b(?:assign(?:ed)?|give|hand|allot)\s+(?:it|this|that|the task)?\s*"
    r"(?:over\s+)?to\s+" + _NAME,
    re.IGNORECASE,
)
_ASK_RE = re.compile(r"^\s*(?:please\s+)?(?:ask|tell|remind|get)\s+" + r"([a-z][a-z.'-]*)" + r"\s+to\s+", re.IGNORECASE)
_PRIORITY_HIGH = re.compile(
    r"[,;]?\s*\b(?:it'?s\s+)?(?:very\s+)?(?:urgent(?:ly)?|asap|as soon as possible|immediately|high priority|"
    r"important)\b[:!]?",
    re.IGNORECASE,
)
_PRIORITY_LOW = re.compile(
    r"[,;]?\s*\b(?:there'?s\s+)?(?:no rush|no hurry|not urgent|low priority|whenever (?:you can|possible))\b",
    re.IGNORECASE,
)
_FILLER_START = re.compile(
    r"^\s*(?:please\s+|can you\s+|could you\s+|we need to\s+|need to\s+|we have to\s+|have to\s+|"
    r"remind (?:me|us|them) to\s+|task\s*[:\-]\s*|to ?do\s*[:\-]\s*|new task\s*[:\-]?\s*)+",
    re.IGNORECASE,
)


def _find_assignee(text: str, members: list[Member], me_id: str | None) -> tuple[Member | None, list[str]]:
    """The matched member and the exact phrases to remove from the title."""
    m = _ASSIGN_RE.search(text)
    if m:
        first, second = m.group(1), m.group(2)
        two = match_member(f"{first} {second}", members, me_id) if second else None
        one = match_member(first, members, me_id)
        if two is not None and second and second.lower() in two[1].lower().split():
            return two, [m.group(0)]
        phrase = m.group(0)
        if second:
            phrase = phrase[: m.start(2) - m.start(0)].rstrip()
        return one, [phrase]
    m = _ASK_RE.search(text)
    if m:
        who = match_member(m.group(1), members, me_id)
        if who is not None:
            return who, [m.group(0)]
    return None, []


def _clean_phrase(s: str) -> str:
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = s.strip(" ,.;:-–—!")
    s = re.sub(r"\s+(?:and|so|then)$", "", s, flags=re.IGNORECASE).strip(" ,.;:-")
    return s


def _strip(sentence: str, remove: list[str]) -> str:
    for phrase in remove:
        sentence = sentence.replace(phrase, " ")
    sentence = _DATE_RE.sub(" ", sentence)
    sentence = _PRIORITY_HIGH.sub(" ", sentence)
    sentence = _PRIORITY_LOW.sub(" ", sentence)
    sentence = _FILLER_START.sub("", sentence)
    return _clean_phrase(sentence)


def _capitalise(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _by_rules(text: str, today: date, members: list[Member], me_id: str | None) -> dict:
    who, remove = _find_assignee(text, members, me_id)
    due = read_due_date(text, today)
    priority = "high" if _PRIORITY_HIGH.search(text) else "low" if _PRIORITY_LOW.search(text) else "normal"

    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    first = sentences[0] if sentences else text
    # "give this to priya: water the plants" -> the task is after the colon.
    title = _strip(first, remove)
    if ":" in title:
        before, after = title.split(":", 1)
        title = _clean_phrase(after) or _clean_phrase(before)
    notes = []
    for s in sentences[1:]:
        cleaned = _strip(s, remove)
        if len(cleaned.split()) >= 4:
            notes.append(_capitalise(cleaned) + ("" if cleaned.endswith((".", "!", "?")) else "."))
    return {
        "title": _capitalise(title)[:255] or None,
        "description": " ".join(notes) or None,
        "due_date": due.isoformat() if due else None,
        "priority": priority,
        "assignee_user_id": who[0] if who else None,
        "assignee_name": who[1] if who else None,
        "source": "rules",
    }


# ---------------------------------------------------------------- Gemini


def _clean_gemini(raw: dict, today: date, members: list[Member], me_id: str | None) -> dict | None:
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    description = raw.get("description")
    description = " ".join(description.split()) if isinstance(description, str) and description.strip() else None
    due = None
    if isinstance(raw.get("due_date"), str):
        try:
            d = date.fromisoformat(raw["due_date"].strip())
            if today - timedelta(days=1) <= d <= today + timedelta(days=3 * 366):
                due = d
        except ValueError:
            due = None
    priority = raw.get("priority") if raw.get("priority") in PRIORITIES else "normal"
    who = match_member(raw.get("assignee_name"), members, me_id)
    return {
        "title": _capitalise(" ".join(title.split()))[:255],
        "description": description[:2000] if description else None,
        "due_date": due.isoformat() if due else None,
        "priority": priority,
        "assignee_user_id": who[0] if who else None,
        "assignee_name": who[1] if who else None,
        "source": "gemini",
    }


# ---------------------------------------------------------------- entry point


def parse_task_text(text: str, today: date, members: list[Member], me_id: str | None = None) -> dict:
    """Read a spoken task into form fields. Raises ValueError for empty text."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Say or type the task first.")
    text = text[:MAX_TEXT_LENGTH]
    if settings.gemini_api_key:
        me_name = next((name for uid, name in members if uid == me_id), "the user")
        prompt = GEMINI_PROMPT.format(
            weekday=today.strftime("%A"),
            today=today.isoformat(),
            names=", ".join(name for _, name in members) or "none",
            me=me_name,
            text=text,
        )
        try:
            raw = understanding.ask_gemini(prompt)
            if isinstance(raw, dict):
                cleaned = _clean_gemini(raw, today, members, me_id)
                if cleaned is not None:
                    return cleaned
        except Exception:  # noqa: BLE001 - any Gemini trouble falls back to the rules
            pass
    return _by_rules(text, today, members, me_id)
