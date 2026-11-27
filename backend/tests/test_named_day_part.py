"""Which part of the day a medicine question is about (narrows the answer), or None for the whole day."""

import pytest

from app.services.understanding import MORNING, NIGHT, NOON, named_day_part


@pytest.mark.parametrize(
    "text, part",
    [
        ("What do I take in the morning?", MORNING),
        ("which medicine this morning", MORNING),
        ("afternoon tablets?", NOON),
        ("what should I take tonight", NIGHT),
        ("night medicine?", NIGHT),
        # Asking about now as well as a part of the day is a whole-day question.
        ("What medicine do I need to take now or in the night?", None),
        ("what do I take today and at night", None),
        ("morning and night medicines?", None),
        ("what medicines do I take?", None),
    ],
)
def test_named_day_part(text, part):
    assert named_day_part(text) == part
