"""Languages supported for parent care profiles and the parent voice chatbot."""

LANGUAGE_CODES: tuple[str, ...] = ("en", "ta", "hi", "te", "ml", "kn")

_NAMES = {
    "english": "en",
    "tamil": "ta",
    "hindi": "hi",
    "telugu": "te",
    "malayalam": "ml",
    "kannada": "kn",
}


def language_code(name_or_code: str | None) -> str:
    """Map a language name or code to a supported code; unknown or missing -> "en"."""
    key = (name_or_code or "").strip().lower()
    if key in LANGUAGE_CODES:
        return key
    return _NAMES.get(key, "en")


def language_name(code: str | None) -> str:
    """The display name the parent profile stores ("Tamil") for a code ("ta"); unknown -> "English"."""
    code = language_code(code)
    return next((name.title() for name, c in _NAMES.items() if c == code), "English")
