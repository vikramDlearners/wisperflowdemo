"""Understanding a parent's spoken answers: urgent health words and medicine replies.

Medicine replies use one Gemini call when online mode is on and a key is set; any failure falls back to the
offline rule-based intent parser, so callers never see an exception.
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.services.adapters.intent import (
    ALLOWED_DELAY_MINUTES,
    CONFIRM_TAKEN,
    MEDICINE_UNAVAILABLE,
    NOT_TAKEN_YET,
    ONLINE_LLM,
    REMIND_LATER,
    RuleBasedIntentParser,
)
from app.services.doses import DueDose
from app.services.prescription_scan import GEMINI_ENDPOINT, GEMINI_TIMEOUT_SECONDS

URGENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "en": (
        "fell", "fall", "fallen", "chest pain", "pain in my chest", "can't breathe", "cannot breathe",
        "breathless", "short of breath", "dizzy", "faint", "fainted", "bleeding", "help", "emergency",
    ),
    "ta": ("விழுந்து", "நெஞ்சு வலி", "மூச்சு விட", "மூச்சுத் திணறல்", "தலை சுற்று", "மயக்கம்", "இரத்தம்", "உதவி", "அவசரம்"),
    "hi": ("गिर गई", "गिर गया", "गिर पड़", "सीने में दर्द", "सांस नहीं", "साँस नहीं", "सांस फूल", "चक्कर", "बेहोश", "खून बह", "मदद", "आपातकाल"),
    "te": ("పడిపోయ", "ఛాతి నొప్పి", "ఛాతీ నొప్పి", "ఊపిరి ఆడ", "తల తిరుగ", "స్పృహ తప్ప", "రక్తస్రావం", "సహాయం", "అత్యవసరం"),
    "ml": ("വീണു", "നെഞ്ചുവേദന", "നെഞ്ച് വേദന", "ശ്വാസം മുട്ട്", "ശ്വാസം കിട്ട", "തലചുറ്റ", "തല ചുറ്റ", "രക്തസ്രാവം", "സഹായിക്കൂ", "സഹായം", "അടിയന്തര"),
    "kn": ("ಬಿದ್ದ", "ಎದೆ ನೋವು", "ಉಸಿರಾಡ", "ಉಸಿರು ಕಟ್ಟ", "ತಲೆ ಸುತ್ತ", "ರಕ್ತಸ್ರಾವ", "ಸಹಾಯ", "ತುರ್ತು"),
}

_LATIN_PATTERNS = [
    re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE)
    for k in URGENT_KEYWORDS["en"]
]
_NON_LATIN_KEYWORDS = tuple(k for lang, ks in URGENT_KEYWORDS.items() if lang != "en" for k in ks)

OUTCOMES = frozenset({"taken", "not_taken", "remind_later", "finished"})
DEFAULT_DELAY_MINUTES = 15
_BARE_NO = frozenset({"no", "nope", "nah", "नहीं"})

_RULE_OUTCOMES = {
    CONFIRM_TAKEN: "taken",
    NOT_TAKEN_YET: "not_taken",
    REMIND_LATER: "remind_later",
    MEDICINE_UNAVAILABLE: "finished",
}


def is_urgent(text: str) -> bool:
    normalised = (text or "").strip().lower().replace("’", "'")
    if not normalised:
        return False
    if any(p.search(normalised) for p in _LATIN_PATTERNS):
        return True
    return any(k in normalised for k in _NON_LATIN_KEYWORDS)


@dataclass
class MedicineAnswer:
    medicine_id: str
    outcome: str  # "taken" | "not_taken" | "remind_later" | "finished"


@dataclass
class MedicineAnswers:
    items: list[MedicineAnswer] = field(default_factory=list)
    delay_minutes: int | None = None
    unclear: bool = False


def ask_gemini(prompt: str) -> dict[str, Any]:
    """The single point that calls Gemini for answer understanding. Tests mock this function."""
    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    request = urllib.request.Request(
        GEMINI_ENDPOINT.format(model=settings.gemini_model),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Gemini request failed with HTTP status {exc.code}") from None
    except (urllib.error.URLError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("Gemini request failed") from None
    try:
        result = json.loads(payload["candidates"][0]["content"]["parts"][0]["text"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not read the Gemini result") from exc
    if not isinstance(result, dict):
        raise ValueError("Could not read the Gemini result")
    return result


def _build_prompt(text: str, due: list[DueDose]) -> str:
    medicines = json.dumps([{"medicine_id": d.medicine_id, "name": d.name} for d in due], ensure_ascii=False)
    return (
        "An elderly person was asked whether they took their medicines. Their reply (any language): "
        f"{json.dumps(text, ensure_ascii=False)}. "
        f"The medicines due now: {medicines}. "
        'For each medicine the reply clearly speaks about, give an outcome: "taken", "not_taken", '
        '"remind_later" (wants a reminder later) or "finished" (ran out). Omit medicines the reply does not '
        "mention and do not guess. If they ask for a later reminder, set delay_minutes to one of "
        "5, 10, 15, 20, 25, 30, else null. Respond only with JSON: "
        '{"answers": [{"medicine_id": string, "outcome": string}], "delay_minutes": number | null}.'
    )


def _from_gemini(text: str, due: list[DueDose]) -> MedicineAnswers:
    result = ask_gemini(_build_prompt(text, due))
    due_ids = {d.medicine_id for d in due}
    items: list[MedicineAnswer] = []
    seen: set[str] = set()
    for raw in result.get("answers") or []:
        if not isinstance(raw, dict):
            continue
        mid, outcome = raw.get("medicine_id"), raw.get("outcome")
        if mid in due_ids and outcome in OUTCOMES and mid not in seen:
            seen.add(mid)
            items.append(MedicineAnswer(mid, outcome))
    if not items:
        return MedicineAnswers(unclear=True)
    delay = result.get("delay_minutes")
    if not isinstance(delay, int) or isinstance(delay, bool) or delay not in ALLOWED_DELAY_MINUTES:
        delay = None
    if any(i.outcome == "remind_later" for i in items):
        delay = delay or DEFAULT_DELAY_MINUTES
    return MedicineAnswers(items=items, delay_minutes=delay)


def _from_rules(text: str, due: list[DueDose]) -> MedicineAnswers:
    if not due:
        return MedicineAnswers(unclear=True)
    result = RuleBasedIntentParser().parse(text)
    outcome = _RULE_OUTCOMES.get(result.intent)
    if outcome is None and (text or "").strip().lower().strip(".!? ") in _BARE_NO:
        outcome = "not_taken"
    if outcome is None:
        return MedicineAnswers(unclear=True)
    if len(due) > 1 and outcome not in ("taken", "not_taken"):
        return MedicineAnswers(unclear=True)
    delay = None
    if outcome == "remind_later":
        delay = result.delay_minutes or DEFAULT_DELAY_MINUTES
    return MedicineAnswers(items=[MedicineAnswer(d.medicine_id, outcome) for d in due], delay_minutes=delay)


def understand_medicines(text: str, due: list[DueDose], mode: str) -> MedicineAnswers:
    if mode == ONLINE_LLM and settings.gemini_api_key and due:
        try:
            return _from_gemini(text, due)
        except Exception:
            pass
    return _from_rules(text, due)
