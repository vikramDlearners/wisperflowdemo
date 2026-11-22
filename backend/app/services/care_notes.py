"""Soft end-of-conversation care notes from what the family wrote on the parent profile.

`deficiencies` (e.g. "Sugar problem, BP") gives gentle everyday reminders; `notes` and `allergies` give a water
target ("3 litres of water daily") and things to avoid ("Allergic to peanuts"). Only what the family wrote is
used, and the wording stays to simple everyday care (less sweets, less salt, water): no medical advice.
"""

import re

# Most useful first; at most MAX_TIPS are said, so the goodbye stays short and soft.
TIP_KEYS = (
    "tip_allergy", "tip_water_amount", "tip_water", "tip_sugar", "tip_bp", "tip_calcium", "tip_iron",
    "tip_vitamin_d", "tip_cholesterol",
)
MAX_TIPS = 3

_CONDITIONS: dict[str, tuple[str, ...]] = {
    "tip_sugar": ("sugar", "diabetes", "diabetic", "glucose", "சர்க்கரை", "நீரிழிவு", "शुगर", "मधुमेह", "डायबिटीज",
                  "షుగర్", "మధుమేహ", "డయాబెటిస్", "ഷുഗർ", "പ്രമേഹ", "ಶುಗರ್", "ಸಕ್ಕರೆ", "ಮಧುಮೇಹ"),
    "tip_bp": ("bp", "blood pressure", "hypertension", "ரத்த அழுத்த", "இரத்த அழுத்த", "பிபி", "बीपी", "रक्तचाप",
               "ब्लड प्रेशर", "బీపీ", "రక్తపోటు", "ബിപി", "രക്തസമ്മർദ", "ಬಿಪಿ", "ರಕ್ತದೊತ್ತಡ"),
    "tip_calcium": ("calcium", "கால்சியம்", "कैल्शियम", "కాల్షియం", "കാൽസ്യം", "ಕ್ಯಾಲ್ಸಿಯಂ"),
    "tip_iron": ("iron", "anaemia", "anemia", "haemoglobin", "hemoglobin", "இரும்புச்சத்து", "ரத்தசோகை", "आयरन",
                 "खून की कमी", "ఐరన్", "రక్తహీనత", "ഇരുമ്പ്", "വിളർച്ച", "ಕಬ್ಬಿಣ", "ರಕ್ತಹೀನತೆ"),
    "tip_vitamin_d": ("vitamin d", "vit d", "vitamin-d", "வைட்டமின் d", "विटामिन d", "విటమిన్ d", "വിറ്റാമിൻ d",
                      "ವಿಟಮಿನ್ d"),
    "tip_cholesterol": ("cholesterol", "கொலஸ்ட்ரால்", "कोलेस्ट्रॉल", "కొలెస్ట్రాల్", "കൊളസ്ട്രോൾ", "ಕೊಲೆಸ್ಟ್ರಾಲ್"),
}
_WATER_WORDS = ("water", "தண்ணீர்", "நீர்", "पानी", "నీళ్ళు", "నీరు", "വെള്ളം", "ನೀರು")
_LITRES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:l\b|ltrs?\b|litres?|liters?|லிட்டர்|लीटर|లీటర్|ലിറ്റർ|ಲೀಟರ್)")
_ALLERGY = re.compile(r"allerg\w*\s*(?:to|:|-)?\s*([^.;\n]+)", re.IGNORECASE)
_NOTHING = frozenset({"none", "nil", "no", "nothing", "na", "n/a", "nka", "-", "none known", "no allergies"})
_SPLIT = re.compile(r"[,;/\n]|\band\b")
_NEGATED = re.compile(r"^\s*(?:no|not|non|without|nahi|नहीं|இல்லை)\b", re.IGNORECASE)


def _has(text: str, word: str) -> bool:
    if word.isascii():
        return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None
    return word in text


def _conditions(deficiencies: str | None) -> list[str]:
    found: list[str] = []
    for part in _SPLIT.split((deficiencies or "").lower()):
        if not part.strip() or _NEGATED.search(part):
            continue
        for key, words in _CONDITIONS.items():
            if key not in found and any(_has(part, w) for w in words):
                found.append(key)
    return found


def _allergy(notes: str | None, allergies: str | None) -> str | None:
    field = " ".join((allergies or "").split())
    if field and field.lower().strip(". ") not in _NOTHING:
        return field[:60]
    match = _ALLERGY.search(notes or "")
    if match:
        item = " ".join(match.group(1).split()).strip(" ,")
        if item and item.lower() not in _NOTHING:
            return item[:60]
    return None


def _water(notes: str | None) -> tuple[str, dict] | None:
    text = (notes or "").lower()
    if not any(_has(text, w) for w in _WATER_WORDS):
        return None
    amount = _LITRES.search(text)
    if amount:
        litres = amount.group(1)
        litres = litres[:-2] if litres.endswith(".0") else litres
        return "tip_water_amount", {"litres": litres}
    return "tip_water", {}


def care_tips(profile) -> list[tuple[str, dict]]:
    """(reply key, values) for the gentle reminders this parent's profile calls for, most useful first."""
    if profile is None:
        return []
    notes = getattr(profile, "notes", None)
    tips: list[tuple[str, dict]] = []
    item = _allergy(notes, getattr(profile, "allergies", None))
    if item:
        tips.append(("tip_allergy", {"item": item}))
    water = _water(notes)
    if water:
        tips.append(water)
    tips += [(key, {}) for key in _conditions(getattr(profile, "deficiencies", None))]
    return tips[:MAX_TIPS]
