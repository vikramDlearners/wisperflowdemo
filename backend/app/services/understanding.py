"""Understanding a parent's spoken answers: urgent health words and medicine replies.

Medicine replies use one Gemini call when online mode is on and a key is set; any failure falls back to the
offline rule-based intent parser, so callers never see an exception.
"""

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.services.adapters.intent import (
    _KEYWORDS as _INTENT_KEYWORDS,
    ALLOWED_DELAY_MINUTES,
    CONFIRM_TAKEN,
    MEDICINE_UNAVAILABLE,
    NOT_TAKEN_YET,
    ONLINE_LLM,
    REMIND_LATER,
    RuleBasedIntentParser,
)
from app.services.doses import DueDose
from app.services.doses import MORNING, NIGHT, NOON
from app.services.prescription_scan import GEMINI_ENDPOINT, GEMINI_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

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
# Obvious English negations and politeness that contain an urgent word. They are removed before matching, so
# "I fell asleep and then I fell down" is still urgent. Kept short on purpose: over-alerting is the safe default.
_URGENT_EXCLUSIONS = re.compile(
    r"\b(?:thank you|thanks|thank u) (?:so much |very much )?for (?:your|the|all your|all the) help\b"
    r"|\b(?:didn't|did not|never|haven't|have not) (?:fall|fallen)\b"
    r"|\bfell asleep\b"
    r"|\bno (?:chest )?pain\b",
    re.IGNORECASE,
)

OUTCOMES = frozenset({"taken", "not_taken", "remind_later", "finished"})
DEFAULT_DELAY_MINUTES = 15
_BARE_NO = frozenset({"no", "nope", "nah", "नहीं", "இல்லை", "illai"})

# "Ran out" only for explicit phrases. The shared intent parser maps bare "finished" and Tamil "இல்லை" (no) to
# MEDICINE_UNAVAILABLE, which is right for its other callers but wrong for a medicine answer, so the medicine rules
# below never use that intent.
_FINISHED_PHRASES: tuple[str, ...] = (
    "ran out", "run out", "running out of", "out of medicine", "out of tablets", "out of pills",
    "no tablets left", "no medicine left", "no pills left", "no more tablets", "no more medicine",
    "tablets finished", "tablets are finished", "tablets have finished", "medicine finished",
    "medicine is finished", "medicine has finished", "medicines finished", "pills finished",
    "தீர்ந்து",  # ta: தீர்ந்துவிட்டது / தீர்ந்து போச்சு (ran out)
    "खत्म हो गई", "खत्म हो गया", "खत्म हो गयी", "दवा खत्म", "दवाई खत्म", "गोली खत्म",
)
# Negations: "not taken". Checked before the "taken" words, because "not taken" contains "taken".
_NEGATION_PHRASES: tuple[str, ...] = (
    "not yet", "not taken", "not now", "haven't", "have not", "didn't", "did not", "not take",
    "இல்லை", "வில்லை",  # ta: no / negative verb ending (எடுக்கவில்லை, சாப்பிடவில்லை)
    "नहीं ली", "नहीं लिया", "नहीं ली है", "नहीं खाई", "नहीं खाया", "अभी तक नहीं", "अभी नहीं",
)
# "Ran out" that is denied or not about medicine. Removed before the ran-out check, so "I haven't run out" is
# never "finished" (alone it is unclear) and "ran out of time, didn't take it" is "not taken".
_NOT_FINISHED = re.compile(
    r"\b(?:haven't|have not|hasn't|has not|hadn't|had not|didn't|did not|not|never|isn't|is not|aren't|are not"
    r"|won't|will not)\s+(?:yet\s+|already\s+)?(?:run|ran|running)\s+out"
    r"(?:\s+of\s+(?:my\s+|the\s+)?(?:medicines?|tablets?|pills?))?(?:\s+yet)?\b"
    r"|\b(?:isn't|is not|aren't|are not|not|haven't|hasn't|have not|has not)\s+(?:yet\s+)?(?:finished|over)\b"
    r"|\bnot\s+out\s+of\s+(?:medicines?|tablets?|pills?)\b"
    r"|\b(?:ran|run|running)\s+out\s+of\s+(?:time|patience)\b"
    # ta: தீர்ந்துவிடவில்லை / தீரவில்லை in one word, or தீர்ந்து followed by a separate இல்லை (has not run out).
    # Never spans into another word: "தீர்ந்துவிட்டது எடுக்கவில்லை" (ran out, didn't take) stays "finished".
    # [஀-௿] is the Tamil block, so punctuation and spaces end the word.
    r"|தீர[஀-௿]*(?:வில்லை|இல்லை)(?![஀-௿])|தீர[஀-௿]*\s+இல்லை(?![஀-௿])"
    r"|(?:दवा|दवाई|गोली)?\s*खत्म\s+नहीं(?:\s+(?:हुई|हुआ|हुयी|है|हुई है|हुआ है))?",  # hi: has not run out
)
# Words that show an answer is about the medicine (used when the reply also has urgent words: "I took a fall").
_MEDICINE_WORDS = re.compile(r"\b(?:medicines?|meds|tablets?|pills?|doses?|capsules?)\b")
# "took both" / "took them" refers to the medicines only when several are due ("hurt both knees" does not).
_TOOK_ALL = re.compile(r"\btook\s+(?:both|them|all)\b")
_MEDICINE_WORDS_NON_LATIN = ("மருந்து", "மாத்திரை", "दवा", "दवाई", "गोली", "మందు", "మాత్ర", "മരുന്ന", "ഗുളിക",
                             "ಔಷಧ", "ಮಾತ್ರೆ")

_RULE_OUTCOMES = {
    CONFIRM_TAKEN: "taken",
    NOT_TAKEN_YET: "not_taken",
    REMIND_LATER: "remind_later",
}


def is_urgent(text: str) -> bool:
    normalised = (text or "").strip().lower().replace("’", "'")
    if not normalised:
        return False
    normalised = _URGENT_EXCLUSIONS.sub(" ", normalised)
    if any(p.search(normalised) for p in _LATIN_PATTERNS):
        return True
    return any(k in normalised for k in _NON_LATIN_KEYWORDS)


# ---------- "I am fine" ----------

_WELL_WORDS = frozenset(
    """fine good great well better okay ok alright wonderful excellent happy fantastic nice perfect normal healthy
    theek thik accha acha achha badhiya nalla nallaa bagunnanu bagunna sukham chennagi chennagiddini
    ठीक अच्छा अच्छी अच्छे बढ़िया बढिया स्वस्थ खुश
    நல்லா நல்ல நன்றாக நலம் நலமாக சந்தோஷமாக
    బాగున్నాను బాగున్నా బాగుంది బాగా బాగానే సంతోషంగా క్షేమంగా
    സുഖം സുഖമാണ് സുഖമായിരിക്കുന്നു നല്ലത് നല്ല നന്നായി നന്നായിരിക്കുന്നു സന്തോഷം
    ಚೆನ್ನಾಗಿದ್ದೇನೆ ಚೆನ್ನಾಗಿದ್ದೀನಿ ಚೆನ್ನಾಗಿದೆ ಚೆನ್ನಾಗಿ ಆರಾಮ ಆರಾಮಾಗಿದ್ದೇನೆ ಸಂತೋಷವಾಗಿದ್ದೇನೆ""".split()
)
_WELL_FILLERS = frozenset(
    """i i'm im am is it's its everything all my health we are feel feeling doing very so really pretty quite
    much just absolutely today now yes yeah hi hello and also thank thanks you god a the day morning afternoon
    evening this slept sleep main mein hoon hu hun bilkul sab bahut irukken naan nenu njan naanu
    मैं में हूँ हूं हू बिल्कुल बिलकुल सब बहुत आज अभी जी हाँ हां है तबीयत तबियत मेरी और धन्यवाद महसूस कर रहा रही
    நான் இருக்கிறேன் இருக்கேன் இன்று இன்னைக்கு மிகவும் ரொம்ப ஆம் எல்லாம் இருக்கு நன்றி
    నేను ఉన్నాను ఉన్నా ఈ రోజు ఈరోజు చాలా అవును అంతా ధన్యవాదాలు
    ഞാൻ ഇന്ന് വളരെ അതെ എല്ലാം എനിക്ക് ആണ് ഇരിക്കുന്നു നന്ദി
    ನಾನು ಇಂದು ಇವತ್ತು ತುಂಬಾ ಹೌದು ಎಲ್ಲಾ ಇದ್ದೇನೆ ಧನ್ಯವಾದಗಳು""".split()
)
_WELL_PHRASES = re.compile(r"\b(?:not bad|no (?:problems?|issues?|complaints?|pain))\b")
_WORD_BREAKS = re.compile(r"[\s.,!?;:।\-–—\"()]+")


def is_all_well(text: str) -> bool:
    """True only when every word says the parent is well ("I am feeling good"). Any other word ("not good",
    "fine but my knee hurts") makes it something the family should hear about."""
    normalised = _WELL_PHRASES.sub(" fine ", (text or "").lower().replace("’", "'"))
    words = [w for w in _WORD_BREAKS.split(normalised) if w]
    return any(w in _WELL_WORDS for w in words) and all(w in _WELL_WORDS or w in _WELL_FILLERS for w in words)


# ---------- "send me the photo of that medicine" / "I'm confused" ----------

_PHOTO_WORDS = re.compile(
    r"\b(?:photos?|photographs?|pictures?|pics?|images?|show me|look like|looks like|tasveer|padam)\b"
)
_PHOTO_WORDS_NON_LATIN = ("போட்டோ", "புகைப்பட", "படம்", "படத்தை", "फोटो", "फ़ोटो", "तस्वीर", "ఫోటో", "చిత్రం",
                          "ഫോട്ടോ", "ചിത്രം", "ಫೋಟೋ", "ಚಿತ್ರ")
# "Can you send me the photo?": a request on its own, without saying of what.
_BARE_PHOTO = re.compile(
    r"(?:please |can you |could you |will you )*(?:send|show|give)(?: me)?(?: the| a| its| that)?"
    r" (?:photo|picture|pic|image)s?(?: again| of it)?(?: please)?"
)
_CONFUSED = re.compile(
    r"\b(?:confused|confusing|confusion|mixed up|(?:not sure|don't know|do not know|can't tell|cannot tell|forgot)"
    r" (?:which|what))\b"
)
_CONFUSED_NON_LATIN = ("குழப்ப", "उलझन", "कन्फ्यूज", "कंफ्यूज", "గందరగోళ", "అయోమయ", "ആശയക്കുഴപ്പ", "കൺഫ്യൂഷൻ", "ಗೊಂದಲ")
_BARE_CONFUSED = re.compile(
    r"(?:(?:i'm|im|i am|am|i feel|feeling|so|very|a bit|a little|little|still|just|now) )*confused(?: now)?"
)
# Not a request to see a medicine: something may have gone wrong with a dose.
_DOSE_MISTAKE = re.compile(r"\b(?:wrong|twice|double|extra|overdose|too many|by mistake)\b")


def _plain(text: str) -> str:
    return " ".join(_WORD_BREAKS.sub(" ", (text or "").lower().replace("’", "'")).split())


def is_bare_confusion(text: str) -> bool:
    """Just "I'm confused": it may be about the medicines, or it may be how the parent feels."""
    plain = _plain(text)
    return bool(_BARE_CONFUSED.fullmatch(plain)) or (
        len(plain.split()) <= 4
        and any(w in plain for w in _CONFUSED_NON_LATIN)
        and not any(w in plain for w in _MEDICINE_WORDS_NON_LATIN)
    )


def is_photo_request(text: str, names_medicine: bool, about_medicines: bool) -> bool:
    """True when the parent asks to see a medicine. `names_medicine`: the text names one of their medicines.
    `about_medicines`: the chat is on the medicine question, so the photo needs no medicine word."""
    plain = _plain(text)
    if not plain or _DOSE_MISTAKE.search(plain):
        return False
    if not (_PHOTO_WORDS.search(plain) or any(w in plain for w in _PHOTO_WORDS_NON_LATIN)):
        return False
    if names_medicine or about_medicines or _BARE_PHOTO.fullmatch(plain):
        return True
    if _MEDICINE_WORDS.search(plain) or any(w in plain for w in _MEDICINE_WORDS_NON_LATIN):
        return True
    return len(plain.split()) <= 3 and any(w in plain for w in _PHOTO_WORDS_NON_LATIN)


def is_medicine_confusion(text: str, names_medicine: bool) -> bool:
    """True for "I'm confused which tablet to take". Never for a dose report or a possible dose mistake."""
    plain = _plain(text)
    if _DOSE_MISTAKE.search(plain) or is_dose_report(text):
        return False
    if not (_CONFUSED.search(plain) or any(w in plain for w in _CONFUSED_NON_LATIN)):
        return False
    return names_medicine or bool(
        _MEDICINE_WORDS.search(plain) or any(w in plain for w in _MEDICINE_WORDS_NON_LATIN)
    )


_NAME_TOKEN = re.compile(r"[^\W_]+")
# Words in a medicine name that do not tell one medicine from another.
_COMMON_NAME_WORDS = frozenset(
    """vitamin vitamins vit tablet tablets tab tabs capsule capsules cap caps pill pills medicine medicines syrup drops
    drop injection cream gel ointment inhaler powder sachet daily morning afternoon evening night day week weekly after
    before food with and for the of to my in on at or one two half mg mcg ml iu gm blood pressure sugar heart pain
    photo picture image show""".split()
)
_VITAMIN_CODE = re.compile(r"[a-z]\d{1,2}")


def _name_tokens(text: str) -> set[str]:
    joined = re.sub(r"\b(vitamin|vit)\.?\s*[- ]?([a-k])[- ]?(\d{1,2})?\b", r"vitamin \2\3", (text or "").lower())
    return set(_NAME_TOKEN.findall(joined.replace("’", "'")))


def named_medicines(text: str, names: dict[str, str]) -> list[str]:
    """The ids of the medicines the text names, matched loosely ("vitamin d 3" is "Vitamin D3 60000 IU"). A word
    shared by many medicines ("vitamin", "tablet") never matches alone. When several fit equally well, all of them
    are returned, so a parent is never shown one of two look-alike names as if it were the only one."""
    said = _name_tokens(text)
    vitamins = {c for c in re.findall(r"vitamin ([a-k])\b", " ".join(_NAME_TOKEN.findall((text or "").lower())))}
    scores: dict[str, int] = {}
    for mid, name in names.items():
        tokens = _name_tokens(name)
        hit = tokens & said
        hit |= {t for t in tokens if _VITAMIN_CODE.fullmatch(t) and t[0] in vitamins and "vitamin" in tokens
                and not any(_VITAMIN_CODE.fullmatch(w) and w[0] == t[0] for w in said)}
        distinctive = {
            t for t in hit - _COMMON_NAME_WORDS
            if _VITAMIN_CODE.fullmatch(t) or (len(t) >= 3 and not t[0].isdigit())
        }
        if distinctive:
            scores[mid] = len(hit)
    best = max(scores.values(), default=0)
    return [mid for mid, score in scores.items() if score == best]


# ---------- questions about the medicine schedule ----------

# "What medicine do I take tonight?" is a question, not a health note or a dose answer: it needs a medicine word
# and a question cue. Answers ("yes I took my tablets") have no question cue.
_QUESTION_CUES_EN = re.compile(
    r"\b(?:what|which|when|what's|whats|tell me|asking about|talking about|list|schedule|do i have|need to take"
    r"|have to take|should i take|do i take|am i taking|to be taken)\b"
)
_QUESTION_CUES_NON_LATIN = (
    "என்ன", "எந்த", "எப்போ", "எப்ப", "எத்தனை",
    "कौन", "क्या", "कब", "कितनी",
    " ఏ ", "ఏమి", "ఏం", "ఏవి", "ఎప్పుడు",
    "ഏത്", "ഏതു", "എന്ത്", "എപ്പോൾ", "ഏതൊക്കെ",
    "ಯಾವ", "ಏನು", "ಯಾವಾಗ",
)


def is_medicine_question(text: str) -> bool:
    """True when the parent asks which medicines to take (now, tonight, today), in any parent language."""
    normalised = (text or "").strip().lower().replace("’", "'")
    if not normalised:
        return False
    if not (_MEDICINE_WORDS.search(normalised) or any(w in normalised for w in _MEDICINE_WORDS_NON_LATIN)):
        return False
    if "?" in normalised or _QUESTION_CUES_EN.search(normalised):
        return True
    padded = f" {normalised} "
    return any(c in padded for c in _QUESTION_CUES_NON_LATIN)


# A medicine question can name a part of the day ("what do I take in the morning?"). English words only;
# other languages fall back to the whole day's answer. A question naming two parts is treated as the whole day.
_DAY_PART_WORDS_EN = {
    MORNING: re.compile(r"\b(?:morning|this morning)\b"),
    NOON: re.compile(r"\b(?:afternoon|noon|midday|mid-day)\b"),
    NIGHT: re.compile(r"\b(?:evening|night|tonight|bedtime)\b"),
}


def named_day_part(text: str) -> str | None:
    """The part of the day a medicine question asks about (morning/noon/night), or None for the whole day."""
    normalised = (text or "").strip().lower()
    matched = [part for part, rx in _DAY_PART_WORDS_EN.items() if rx.search(normalised)]
    return matched[0] if len(matched) == 1 else None


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


def _rule_outcome(normalised: str) -> str | None:
    """The medicine outcome for a reply, or None. Explicit "ran out" phrases, then negations, then the shared
    intent keywords except MEDICINE_UNAVAILABLE (so "finished breakfast and took it" is "taken").
    Denied or non-medicine "ran out" phrases are removed first."""
    normalised = _NOT_FINISHED.sub(" ", normalised)
    if any(p in normalised for p in _FINISHED_PHRASES):
        return "finished"
    if normalised.strip(".!?, ") in _BARE_NO:
        return "not_taken"
    if " ".join(re.sub(r"[.,!?।]+", " ", normalised).split()) in _BARE_YES:
        return "taken"  # a bare "yes" in any parent language answers "Did you take ...?"
    remind = any(k in normalised for intent, ks in _INTENT_KEYWORDS if intent == REMIND_LATER for k in ks)
    if any(p in normalised for p in _NEGATION_PHRASES) and not remind:
        return "not_taken"
    for intent, keywords in _INTENT_KEYWORDS:
        if intent == MEDICINE_UNAVAILABLE:
            continue
        if any(k in normalised for k in keywords):
            return _RULE_OUTCOMES.get(intent)
    return None


def _mentions_medicine(normalised: str, due: list[DueDose]) -> bool:
    if _MEDICINE_WORDS.search(normalised) or any(w in normalised for w in _MEDICINE_WORDS_NON_LATIN):
        return True
    if len(due) > 1 and _TOOK_ALL.search(normalised):
        return True
    return any(d.name and d.name.lower() in normalised for d in due)


def _from_rules(text: str, due: list[DueDose]) -> MedicineAnswers:
    if not due:
        return MedicineAnswers(unclear=True)
    normalised = (text or "").strip().lower().replace("’", "'")
    outcome = _rule_outcome(normalised)
    if outcome == "taken" and is_urgent(text) and not _mentions_medicine(normalised, due):
        outcome = None  # "I took a fall" is not a dose taken
    if outcome is None:
        return MedicineAnswers(unclear=True)
    if len(due) > 1 and outcome not in ("taken", "not_taken"):
        return MedicineAnswers(unclear=True)
    delay = None
    if outcome == "remind_later":
        delay = RuleBasedIntentParser._extract_delay(normalised) or DEFAULT_DELAY_MINUTES
    return MedicineAnswers(items=[MedicineAnswer(d.medicine_id, outcome) for d in due], delay_minutes=delay)


def understand_medicines(text: str, due: list[DueDose], mode: str) -> MedicineAnswers:
    if mode == ONLINE_LLM and settings.gemini_api_key and due:
        try:
            return _from_gemini(text, due)
        except Exception as exc:  # noqa: BLE001 - any failure falls back to the offline rules
            # Only the exception type and its own message (never the key or the parent's words).
            logger.warning("Gemini medicine understanding failed, using offline rules: %s: %s",
                           type(exc).__name__, exc)
    return _from_rules(text, due)

# ---------- how many medicines did the parent take? ----------

ALL, NONE = "all", "none"
_ALL_WORDS = (
    "both", "all", "every", "each", "them all", "all of them", "took them",
    "எல்லா", "இரண்டும்", "ரெண்டும்", "எல்லாமே",
    "दोनों", "सब", "सभी", "सारी", "सारे",
    "రెండూ", "అన్నీ", "అన్ని",
    "രണ്ടും", "എല്ലാം",
    "ಎರಡೂ", "ಎಲ್ಲಾ", "ಎಲ್ಲವೂ",
)
_NONE_WORDS = ("none", "nothing", "zero", "not any", "no medicine", "ஒன்றும்", "ஒன்னும்", "कोई नहीं", "एक भी नहीं",
               "ఏదీ", "ఒక్కటీ", "ഒന്നും", "ಯಾವುದೂ", "ಒಂದೂ")
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "only one": 1, "just one": 1,
    "ஒன்று": 1, "ஒண்ணு": 1, "இரண்டு": 2, "ரெண்டு": 2, "மூன்று": 3, "மூணு": 3,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4,
    "ఒకటి": 1, "ఒక్కటి": 1, "రెండు": 2, "మూడు": 3,
    "ഒന്ന്": 1, "ഒരെണ്ണം": 1, "രണ്ട്": 2, "മൂന്ന്": 3,
    "ಒಂದು": 1, "ಎರಡು": 2, "ಮೂರು": 3,
}
_LATIN_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")
# A bare "yes" answers "Did you take them?" for the whole list.
_BARE_YES = frozenset({
    "yes", "yeah", "yep", "yes i did", "i did", "done", "yes done", "haan", "ha",
    "ஆமா", "ஆம்", "ஆமாம்", "हाँ", "हां", "जी हाँ", "जी", "అవును", "ఔను", "അതെ", "ಹೌದು",
})


def _has_word(normalised: str, word: str) -> bool:
    if word.isascii():
        return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", normalised) is not None
    return word in normalised


def count_scope(text: str, due: list[DueDose]):
    """How much of the due list a "took" reply covers: ALL, NONE, a number, or the medicine ids it names.
    None when the reply does not say ("I took my medicine")."""
    normalised = (text or "").strip().lower().replace("’", "'")
    if not normalised:
        return None
    if re.sub(r"[.,!?।]+", " ", normalised).split() and " ".join(
        re.sub(r"[.,!?।]+", " ", normalised).split()
    ) in _BARE_YES:
        return ALL
    named = [d.medicine_id for d in due if d.name and d.name.lower() in normalised]
    if named:
        return list(dict.fromkeys(named))
    if any(_has_word(normalised, w) for w in _NONE_WORDS):
        return NONE
    if any(_has_word(normalised, w) for w in _ALL_WORDS):
        return ALL
    digits = re.findall(r"\b\d+\b", normalised)
    if digits:
        return int(digits[0])
    for word, number in sorted(_NUMBER_WORDS.items(), key=lambda kv: -len(kv[0])):
        if _has_word(normalised, word):
            return number
    return None


_OFFER_YES = frozenset(
    """yes yeah yep sure ok okay show see want haan
    ஆமா ஆம் ஆமாம் சரி வேண்டும் காட்டு காட்டுங்கள் हाँ हां जी ठीक दिखाओ दिखाइए అవును ఔను సరే చూపించు చూపించండి
    അതെ ശരി വേണം കാണണം കാണിക്കൂ ಹೌದು ಸರಿ ಬೇಕು ತೋರಿಸಿ""".split()
)
_OFFER_NO = frozenset("no nope nah not don't illai இல்லை வேண்டாம் नहीं मत వద్దు లేదు വേണ്ട ഇല്ല ಬೇಡ ಇಲ್ಲ".split())
_OFFER_FILLERS = frozenset(
    """please me them it the a i i'd would like to can you could need thanks thank images image photos photo
    pictures picture pics of medicines medicine tablets है""".split()
)


def is_bare_yes(text: str) -> bool:
    """A "yes" that says nothing more ("yes", "yes please", "ஆமா")."""
    words = _plain(text).split()
    return any(w in _OFFER_YES for w in words) and all(w in _OFFER_YES or w in _OFFER_FILLERS for w in words)


def is_bare_no(text: str) -> bool:
    """A "no" that says nothing more ("no", "no thank you", "வேண்டாம்")."""
    words = _plain(text).split()
    polite = ("please", "thanks", "thank", "you")
    return any(w in _OFFER_NO for w in words) and all(w in _OFFER_NO or w in polite for w in words)


def photo_offer_answer(text: str) -> bool | None:
    """The answer to "Do you want to see the images?": True or False, or None when the text says anything more
    (such as "yes, I took them", which is about the doses)."""
    words = _plain(text).split()
    if not words or not all(w in _OFFER_YES or w in _OFFER_NO or w in _OFFER_FILLERS for w in words):
        return None
    if any(w in _OFFER_NO for w in words):
        return False
    return True if any(w in _OFFER_YES for w in words) or is_photo_request(text, False, True) else None


def is_dose_report(text: str) -> bool:
    """"I took my evening tablets": a medicine word and a taken answer, and not a question."""
    normalised = (text or "").strip().lower().replace("’", "'")
    if not normalised or is_medicine_question(text):
        return False
    mentions = _MEDICINE_WORDS.search(normalised) or any(w in normalised for w in _MEDICINE_WORDS_NON_LATIN)
    return bool(mentions) and _rule_outcome(normalised) == "taken"
