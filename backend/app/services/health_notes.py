"""Health notes: allergies, conditions and readings read from what the parent says or uploads, and food
advice that respects them.

`read_notes(text)` finds what a message says about health ("My BP is high now", "sugar 180 today",
"I'm allergic to peanuts"). `save_found` stores it, once per allergy or condition and every reading.
`health_summary` merges these notes with what the family wrote on the parent profile, and `food_ideas` /
`can_eat` answer food questions from it: never a food the parent is allergic to, and suited to their
conditions. Staging and commits follow the other services: the caller commits.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care_profile import CareProfile
from app.models.health_note import ALLERGY, CONDITION, READING, HealthNote
from app.models.meal import MealLog
from app.services.care_notes import _CONDITIONS, _NOTHING, _has
from app.services import doses

# ---------- reading what a message says ----------

BP, SUGAR, WEIGHT, PULSE = "bp", "sugar", "weight", "pulse"
READING_LABELS = {BP: "BP", SUGAR: "Sugar", WEIGHT: "Weight", PULSE: "Pulse"}
READING_UNITS = {BP: "mmHg", SUGAR: "mg/dL", WEIGHT: "kg", PULSE: "bpm"}
HIGH, LOW, NORMAL = "high", "low", "normal"

# Condition names for the care_notes keyword groups, as the family sees them.
CONDITION_NAMES = {
    "tip_sugar": "Sugar (diabetes)",
    "tip_bp": "BP",
    "tip_cholesterol": "Cholesterol",
    "tip_iron": "Low iron",
    "tip_calcium": "Low calcium",
    "tip_vitamin_d": "Low vitamin D",
}
# Groups that are a problem only when the parent says they have it ("I have low iron"), not when named.
_NEEDS_CUE = frozenset({"tip_iron", "tip_calcium", "tip_vitamin_d"})

_CLAUSES = re.compile(r"(?<!\d)\.|\.(?!\d)|[;!?\n]|,\s*(?:but|and|also)\b|\bbut\b")
_NUMBER_BP = re.compile(r"\b(?:bp|b\.p\.?|blood pressure|pressure)\b[^0-9\n]{0,25}?(\d{2,3})\s*(?:/|over|by)\s*(\d{2,3})")
_NUMBER = {
    SUGAR: re.compile(r"\b(?:sugar|glucose|fbs|ppbs|rbs)\b[^0-9\n]{0,25}?(\d{2,3})\b"),
    WEIGHT: re.compile(r"\b(?:weight|weigh|weighed|weighing)\b[^0-9\n]{0,15}?(\d{2,3}(?:\.\d)?)\b"),
    PULSE: re.compile(r"\b(?:pulse|heart ?rate)\b[^0-9\n]{0,15}?(\d{2,3})\b"),
}
_HIGH_WORDS = ("high", "up", "raised", "increased", "shot up", "too much", "அதிகம்", "அதிகமா", "ज्यादा", "ज़्यादा",
               "बढ़", "हाई", "ఎక్కువ", "పెరిగ", "കൂടുതൽ", "കൂടി", "ಹೆಚ್ಚು", "ಜಾಸ್ತಿ")
_LOW_WORDS = ("low", "down", "dropped", "குறைவு", "குறைந்", "कम", "लो", "తక్కువ", "తగ్గ", "കുറവ്", "കുറഞ്ഞ", "ಕಡಿಮೆ")
_NORMAL_WORDS = ("normal", "fine", "okay", "ok", "under control", "controlled", "சரியா", "नॉर्मल", "ठीक")
_NOT_HIGH = re.compile(r"\bnot\s+(?:high|low|up)\b")
_HAVE_CUES = re.compile(
    r"\b(?:i have|i've got|i have got|i got|have got|diagnosed|suffering|suffer|problem|issue|patient|"
    r"deficien\w*|doctor said|doctor says|told me|i am diabetic|i'm diabetic)\b"
    r"|எனக்கு|பிரச்சனை|मुझे|समस्या|बीमारी|నాకు|സമസ്യ|എനിക്ക്|ನನಗೆ"
)
_DIAGNOSED = re.compile(r"\bdiagnosed (?:with|as having)\s+([a-z][a-z \-']{2,60})")
_ALLERGY_TO = re.compile(r"\b(?:allergic|allergy|allergies)\s*(?:to|from|with|for|:|-)\s*([^.;\n!?]+)")
_ALLERGY_OF = re.compile(r"\b((?:[a-z\-]+ )?[a-z\-]+) allergy\b")
_NOT_ALLERGEN = frozenset({"an", "a", "the", "have", "some", "my", "food", "skin", "any", "no", "got"})
_ALLERGY_HI = re.compile(r"(\S+)\s+से\s+एलर्जी")
_ALLERGY_TRIM = re.compile(r"\b(?:now|also|too|since \w+|i think|please note|so)\b.*$")
_ALLERGY_SPLIT = re.compile(r",|\band\b|\bor\b|&|/")
_NEGATED = re.compile(r"^\s*(?:no|not|non|without|never|nahi|नहीं|இல்லை)\b|\b(?:no|not|don't have|do not have)\s+(?:any\s+)?"
                      r"(?:allerg|bp|sugar|diabet|problem)")


@dataclass(frozen=True)
class Found:
    kind: str
    label: str
    value: str | None = None
    value_num: float | None = None
    value_num2: float | None = None


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in _CLAUSES.split((text or "").lower().replace("’", "'")) if c.strip()]


def _level(clause: str) -> str | None:
    if _NOT_HIGH.search(clause):
        return NORMAL
    if any(_has(clause, w) for w in _HIGH_WORDS):
        return HIGH
    if any(_has(clause, w) for w in _LOW_WORDS):
        return LOW
    if any(_has(clause, w) for w in _NORMAL_WORDS):
        return NORMAL
    return None


# Everyday words for sugar and BP that the profile keywords in care_notes do not have.
_SPOKEN = {"tip_sugar": ("சுகர்", "शक्कर", "sugar level"), "tip_bp": ("pressure", "பிரஷர்", "प्रेशर", "ప్రెషర్")}
_GROUP_WORDS = {key: words + _SPOKEN.get(key, ()) for key, words in _CONDITIONS.items()}


def _groups_in(clause: str) -> list[str]:
    return [key for key, words in _GROUP_WORDS.items() if any(_has(clause, w) for w in words)]


def _num(text: str) -> float:
    return float(text)


def _readings(clause: str) -> list[Found]:
    found: list[Found] = []
    bp = _NUMBER_BP.search(clause)
    if bp:
        high, low = int(bp.group(1)), int(bp.group(2))
        if 60 <= high <= 260 and 30 <= low <= 160:
            found.append(Found(READING, BP, f"{high}/{low}", float(high), float(low)))
    for label, pattern in _NUMBER.items():
        match = pattern.search(clause)
        if match:
            found.append(Found(READING, label, match.group(1), _num(match.group(1))))
    named = {f.label for f in found}
    level = _level(clause)
    if level:
        groups = _groups_in(clause)
        for label, group in ((BP, "tip_bp"), (SUGAR, "tip_sugar")):
            if group in groups and label not in named:
                found.append(Found(READING, label, level))
    return found


def _allergies(clause: str) -> list[Found]:
    items: list[str] = []
    match = _ALLERGY_TO.search(clause)
    of = None if match else _ALLERGY_OF.search(clause)
    if of:
        words = of.group(1).split()
        while words and words[0] in _NOT_ALLERGEN:
            words.pop(0)
        if words and words[-1] not in _NOT_ALLERGEN:
            items.append(" ".join(words))
    if match:
        raw = match.group(1)
        raw = _ALLERGY_TRIM.sub("", raw)
        raw = re.sub(r"^(?:i have (?:an? )?|i'm |i am |have (?:an? )?|an? |some |to |my )+", "", raw.strip())
        items += [p.strip(" ,'\"") for p in _ALLERGY_SPLIT.split(raw)]
    for hi in _ALLERGY_HI.finditer(clause):
        items.append(hi.group(1).strip())
    out: list[Found] = []
    for item in items:
        item = re.sub(r"^(?:the|a|an)\s+", "", item)
        if 2 <= len(item) <= 60 and item not in _NOTHING and item not in ("allergy", "allergic", "food", "something"):
            out.append(Found(ALLERGY, item))
    return out


def _conditions(clause: str, readings: list[Found]) -> list[Found]:
    found: list[Found] = []
    cue = _HAVE_CUES.search(clause) is not None
    levels = {r.label: r.value for r in readings if r.value in (HIGH, LOW)}
    for group in _groups_in(clause):
        reading_label = {"tip_bp": BP, "tip_sugar": SUGAR}.get(group)
        # Low sugar on its own is a reading, not diabetes.
        out_of_range = reading_label in levels and not (group == "tip_sugar" and levels[reading_label] == LOW)
        if group in _NEEDS_CUE and not cue:
            continue
        if not (cue or out_of_range or group == "tip_sugar" and re.search(r"\bdiabet", clause)):
            continue
        detail = levels.get(reading_label) if reading_label else None
        found.append(Found(CONDITION, CONDITION_NAMES[group], detail))
    diagnosed = _DIAGNOSED.search(clause)
    if diagnosed and not found:
        name = diagnosed.group(1).strip(" -'")
        found.append(Found(CONDITION, name[:1].upper() + name[1:]))
    return found


NOTHING = _NOTHING


def parse_reading(kind: str | None, value: str | None) -> Found | None:
    """A reading from a label and a value written on a document: ("bp", "140/90"), ("sugar", "high")."""
    kind, value = (kind or "").lower(), (value or "").lower().strip()
    if kind not in READING_LABELS or not value:
        return None
    if kind == BP:
        match = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", value)
        if match:
            return Found(READING, BP, f"{match[1]}/{match[2]}", float(match[1]), float(match[2]))
    else:
        match = re.search(r"\d{2,3}(?:\.\d)?", value)
        if match:
            return Found(READING, kind, match[0], float(match[0]))
    level = _level(value)
    return Found(READING, kind, level) if level else None


def read_notes(text: str) -> list[Found]:
    """Everything a message says about health, at most once each, in the order it was said."""
    found: list[Found] = []
    for clause in _clauses(text):
        allergy_negated = re.search(r"\b(?:no|not|don't have|do not have|never had)\b[^.]{0,15}allerg", clause)
        if not allergy_negated:
            found += _allergies(clause)
        if _NEGATED.search(clause) and not re.search(r"\d", clause):
            continue
        readings = _readings(clause)
        found += readings + _conditions(clause, readings)
    unique: list[Found] = []
    for f in found:
        if f not in unique:
            unique.append(f)
    return unique


# ---------- storing ----------

def active_notes(db: Session, care_profile_id: str, kind: str | None = None) -> list[HealthNote]:
    query = select(HealthNote).where(HealthNote.care_profile_id == care_profile_id, HealthNote.active.is_(True))
    if kind:
        query = query.where(HealthNote.kind == kind)
    return list(db.execute(query.order_by(HealthNote.recorded_at, HealthNote.id)).scalars())


def _same_label(a: str, b: str) -> bool:
    return a.strip().lower().rstrip("s") == b.strip().lower().rstrip("s")


def save_found(
    db: Session, profile: CareProfile, found: list[Found], source: str, source_text: str | None,
    user_id: str | None, now: datetime,
) -> list[HealthNote]:
    """Stage new notes: every reading, and allergies and conditions not on the list yet (a condition's
    detail is updated). Returns the rows staged or changed."""
    saved: list[HealthNote] = []
    existing = active_notes(db, profile.id)
    for f in found:
        if f.kind != READING:
            same = next((n for n in existing if n.kind == f.kind and _same_label(n.label, f.label)), None)
            if same is not None:
                if f.value and same.value != f.value:
                    same.value, same.recorded_at = f.value, now
                    saved.append(same)
                continue
        row = HealthNote(
            family_id=profile.family_id, care_profile_id=profile.id, kind=f.kind, label=f.label, value=f.value,
            value_num=f.value_num, value_num2=f.value_num2, source=source,
            source_text=(source_text or "")[:2000] or None, recorded_by_user_id=user_id, recorded_at=now,
        )
        db.add(row)
        existing.append(row)
        saved.append(row)
    return saved


def describe(note: HealthNote, profile: CareProfile | None = None) -> str:
    """One short line for a note, as the parent and family read it: "BP 140/90 mmHg", "allergy to peanuts"."""
    if note.kind == ALLERGY:
        return f"allergy to {note.label}"
    if note.kind == CONDITION:
        return f"{note.label} ({note.value})" if note.value else note.label
    name = READING_LABELS.get(note.label, note.label)
    if note.value in (HIGH, LOW, NORMAL):
        return f"{name} {note.value}"
    unit = READING_UNITS.get(note.label)
    return f"{name} {note.value} {unit}" if unit else f"{name} {note.value}"


# ---------- what is known about the parent ----------

@dataclass
class HealthSummary:
    allergies: list[str] = field(default_factory=list)
    # care_notes keyword groups (tip_bp, tip_sugar, ...) for the conditions known
    groups: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)


def _profile_fields(db: Session, profile: CareProfile):
    from app.services.profile import get_care_profile_onboarding

    return get_care_profile_onboarding(db, profile)


def _split_items(text: str | None) -> list[str]:
    items = [" ".join(p.split()).strip(" .") for p in re.split(r"[,;/\n]|\band\b", text or "")]
    return [i for i in items if i and i.lower() not in _NOTHING]


def health_summary(db: Session, profile: CareProfile) -> HealthSummary:
    summary = HealthSummary()
    fields = _profile_fields(db, profile)
    allergies = [n.label for n in active_notes(db, profile.id, ALLERGY)]
    conditions = [n.label for n in active_notes(db, profile.id, CONDITION)]
    if fields is not None:
        allergies += _split_items(getattr(fields, "allergies", None))
        written = " , ".join(filter(None, (getattr(fields, "known_health_conditions", None),
                                            getattr(fields, "deficiencies", None))))
        conditions += _split_items(written)
        for f in read_notes(getattr(fields, "notes", None) or ""):
            if f.kind == ALLERGY:
                allergies.append(f.label)
    for item in allergies:
        if not any(_same_label(item, a) for a in summary.allergies):
            summary.allergies.append(item)
    for item in conditions:
        if not any(_same_label(item, c) for c in summary.conditions):
            summary.conditions.append(item)
        for group in _groups_in(item.lower()):
            if group not in summary.groups:
                summary.groups.append(group)
    return summary


# ---------- food ----------

# Common allergens and the words that name them in an allergy or a dish.
ALLERGENS: dict[str, tuple[str, ...]] = {
    "peanut": ("peanut", "groundnut", "moongphali", "kadalai", "verkadalai"),
    "nuts": ("nut", "cashew", "almond", "badam", "walnut", "pista", "pistachio", "kaju"),
    "milk": ("milk", "dairy", "lactose", "curd", "yogurt", "yoghurt", "paneer", "ghee", "buttermilk", "cheese",
             "butter", "dahi"),
    "wheat": ("wheat", "gluten", "atta", "maida", "chapati", "roti", "rava", "sooji", "semolina", "bread"),
    "egg": ("egg",),
    "fish": ("fish", "seafood", "prawn", "shrimp", "shellfish", "crab"),
    "soy": ("soy", "soya", "tofu"),
    "sesame": ("sesame", "til", "gingelly"),
}


@dataclass(frozen=True)
class Food:
    name: str
    meals: tuple[str, ...]
    contains: tuple[str, ...] = ()
    good_for: tuple[str, ...] = ()
    # care_notes groups this food is not kind to
    bad_for: tuple[str, ...] = ()


B, L, D, S = "breakfast", "lunch", "dinner", "snack"
FOODS: tuple[Food, ...] = (
    Food("idli with sambar", (B, D), (), ("tip_bp", "tip_cholesterol")),
    Food("ragi dosa", (B, D), (), ("tip_sugar", "tip_calcium", "tip_iron")),
    Food("moong dal chilla", (B,), (), ("tip_sugar", "tip_iron")),
    Food("oats porridge with milk", (B,), ("milk",), ("tip_sugar", "tip_cholesterol", "tip_bp")),
    Food("vegetable upma", (B,), ("wheat",), ("tip_bp",)),
    Food("vegetable poha with peanuts", (B,), ("peanut",), ("tip_iron",)),
    Food("boiled egg with toast", (B,), ("egg", "wheat"), ("tip_vitamin_d",)),
    Food("brown rice with dal and vegetables", (L,), (), ("tip_sugar", "tip_bp")),
    Food("chapati with mixed vegetable sabzi", (L, D), ("wheat",), ("tip_sugar", "tip_cholesterol")),
    Food("palak dal with rice", (L,), (), ("tip_iron",)),
    Food("curd rice", (L,), ("milk",), ("tip_calcium",)),
    Food("rajma with brown rice", (L,), (), ("tip_iron", "tip_sugar")),
    Food("grilled fish with rice", (L,), ("fish",), ("tip_vitamin_d", "tip_cholesterol")),
    Food("vegetable khichdi", (L, D), (), ("tip_bp", "tip_sugar")),
    Food("jowar or ragi roti with dal", (D,), (), ("tip_sugar", "tip_calcium")),
    Food("vegetable soup with chapati", (D,), ("wheat",), ("tip_bp", "tip_cholesterol")),
    Food("paneer and vegetable stir fry", (D,), ("milk",), ("tip_calcium",)),
    Food("tofu bhurji", (D,), ("soy",), ("tip_calcium", "tip_cholesterol")),
    Food("roasted chana", (S,), (), ("tip_sugar", "tip_iron")),
    Food("sprouts salad", (S,), (), ("tip_iron", "tip_sugar")),
    Food("a guava or an apple", (S,), (), ("tip_bp", "tip_sugar")),
    Food("plain buttermilk", (S,), ("milk",), ("tip_calcium", "tip_bp")),
    Food("a few almonds and walnuts", (S,), ("nuts",), ("tip_cholesterol",)),
    Food("a banana", (S,), (), ("tip_bp",), ("tip_sugar",)),
    Food("a small til laddu", (S,), ("sesame",), ("tip_calcium",), ("tip_sugar",)),
)
# What to go easy on for each condition, and the words that name such food in a question.
GO_EASY: dict[str, tuple[str, tuple[str, ...]]] = {
    "tip_sugar": ("sweets, sugary tea and fruit juice",
                  ("sweet", "sugar", "mithai", "laddu", "ladoo", "jalebi", "halwa", "payasam", "kheer", "cake",
                   "chocolate", "ice cream", "juice", "gulab jamun", "rasgulla", "biscuit", "mango", "honey")),
    "tip_bp": ("pickles, papad and salty snacks",
               ("pickle", "achar", "papad", "chips", "namkeen", "salt", "salty", "mixture", "dried fish")),
    "tip_cholesterol": ("fried and oily food",
                        ("fried", "fry", "pakora", "bajji", "samosa", "vada", "puri", "poori", "bonda", "oily",
                         "butter", "ghee")),
}
_FOOD_QUESTION = re.compile(
    r"\b(?:what|which|suggest|recommend|ideas?|good)\b.{0,40}\b(?:eat|food|foods|meal|breakfast|lunch|dinner|"
    r"snacks?|diet|cook)\b"
    r"|\bwhat (?:can|should|shall) i (?:eat|have|cook)\b|\bfood (?:advice|ideas?|suggestions?)\b"
    r"|क्या खा|என்ன சாப்பிட|ఏమి తిన|എന്ത് കഴിക്ക|ಏನು ತಿನ್ನ"
)
_CAN_EAT = re.compile(
    r"\b(?:can|may|should|could) i (?:eat|have|take|drink)\s+(?:some |a |an |the )?(.+?)\s*(?:\?|$|today|now|tonight)"
    r"|\bis (?:it )?(?:ok|okay|fine|safe|good) (?:for me )?to (?:eat|have|drink)\s+(?:some |a |an )?(.+?)\s*(?:\?|$)"
)

_ANY_FOOD = re.compile(r"^(?:for |at |in )?(?:the )?(?:breakfast|lunch|dinner|snacks?|tiffin|something|anything|food)\b")


def is_food_question(text: str) -> bool:
    low = (text or "").lower()
    return bool(_FOOD_QUESTION.search(low) or _CAN_EAT.search(low))


def _allergen_keys(item: str) -> set[str]:
    low = item.lower()
    return {key for key, words in ALLERGENS.items() if any(w in low for w in words)}


def _allergy_hits(food_text: str, contains: tuple[str, ...], allergies: list[str]) -> str | None:
    """The allergy this food would break, if any."""
    low = food_text.lower()
    for allergy in allergies:
        keys = _allergen_keys(allergy)
        if keys & set(contains) or keys & _allergen_keys(low):
            return allergy
        words = [w.rstrip("s") for w in re.findall(r"[a-z]{3,}", allergy.lower())]
        if any(w and w in low for w in words):
            return allergy
    return None


def _meal_for(text: str, profile: CareProfile, now: datetime) -> str:
    low = (text or "").lower()
    for meal in (B, L, D):
        if meal in low:
            return meal
    if re.search(r"\bsnacks?\b|evening tea|tiffin", low):
        return S
    part = doses.day_part(doses.local_now(profile, now))
    return B if part == doses.MORNING else L if part == doses.NOON else D


def _cooked_at_home(db: Session, profile: CareProfile, now: datetime) -> str:
    since = doses.local_now(profile, now).date() - timedelta(days=30)
    rows = db.execute(
        select(MealLog.text).where(MealLog.care_profile_id == profile.id, MealLog.log_date >= since)
    ).scalars()
    return " ".join(rows).lower()


@dataclass
class FoodAdvice:
    meal: str
    foods: list[str]
    allergies: list[str]
    # care_notes groups the advice was suited to
    groups: list[str]
    go_easy: list[str]


def food_ideas(db: Session, profile: CareProfile, text: str, now: datetime, count: int = 3) -> FoodAdvice:
    """A few foods for the meal asked about (or the one due now): none the parent is allergic to, none
    unkind to their conditions, those that help their conditions and those the family cooks first."""
    summary = health_summary(db, profile)
    meal = _meal_for(text, profile, now)
    cooked = _cooked_at_home(db, profile, now)
    groups = summary.groups

    def score(food: Food) -> tuple[int, int]:
        home = any(w in cooked for w in re.findall(r"[a-z]{4,}", food.name) if w not in ("with", "rice"))
        helps = len(set(food.good_for) & set(groups))
        return (-int(home), -helps)

    safe = [
        f for f in FOODS
        if meal in f.meals and not _allergy_hits(f.name, f.contains, summary.allergies)
        and not set(f.bad_for) & set(groups)
    ]
    chosen = [f.name for f in sorted(safe, key=score)[:count]]
    return FoodAdvice(meal=meal, foods=chosen, allergies=summary.allergies, groups=groups,
                      go_easy=[GO_EASY[g][0] for g in groups if g in GO_EASY])


@dataclass
class CanEat:
    food: str
    # "allergy", "go_easy" or "ok"
    verdict: str
    allergy: str | None = None
    group: str | None = None


def can_eat(db: Session, profile: CareProfile, text: str) -> CanEat | None:
    """For "Can I eat X?": whether X breaks an allergy or is unkind to a condition. None if not such a question."""
    match = _CAN_EAT.search((text or "").lower())
    if not match:
        return None
    food = (match.group(1) or match.group(2) or "").strip(" .?!")
    if not food or _ANY_FOOD.match(food):
        return None  # "What can I eat for lunch?" asks for ideas, not about one food
    summary = health_summary(db, profile)
    allergy = _allergy_hits(food, (), summary.allergies)
    if allergy:
        return CanEat(food, "allergy", allergy=allergy)
    for group in summary.groups:
        words = GO_EASY.get(group, ("", ()))[1]
        if any(w in food for w in words):
            return CanEat(food, "go_easy", group=group)
    return CanEat(food, "ok")
