"""Pulling a place name out of a facility request.

Shared by the supervisor, which needs to know whether a message names a
place at all, and the graph, which looks the place up.
"""

import re

# fmt: off
GENERIC_TERMS = {
    "hospital", "hospitals", "doctor", "doctors", "clinic", "clinics",
    "specialist", "specialists", "cardiologist", "dermatologist", "dentist",
    "neurologist", "orthopedic", "gynecologist", "pediatrician", "physician",
    "ent specialist", "me", "us", "here", "somewhere", "my", "area", "location",
    "a", "the", "any", "some", "good", "best", "nearby",
}
# fmt: on

# Word-bounded, so "in" inside "find" or "clinic" never counts.
_PLACE_PREPOSITION = re.compile(r"\b(?:near|nearby|in|at|around|close to)\s+", re.IGNORECASE)

# What follows the place is usually a purpose, not more place:
# "hospitals in Delhi for heart problems".
_TRAILING_CLAUSE = re.compile(
    r"\s+(?:for|with|that|which|who|where|please|pls|asap|urgently|right now)\b.*$",
    re.IGNORECASE,
)


def extract_location(query: str) -> str:
    """The place a facility request names, or "" if it names none.

    The last preposition wins: in "nearby hospital in Mumbai" the place is
    what follows "in", not the "hospital in Mumbai" that follows "nearby" -
    which is what used to be sent to the geocoder.
    """

    text = query or ""

    for match in reversed(list(_PLACE_PREPOSITION.finditer(text))):
        candidate = _TRAILING_CLAUSE.sub("", text[match.end() :]).strip(" .,?!;:")
        words = candidate.lower().split()

        if words and not all(word in GENERIC_TERMS for word in words):
            return candidate

    return ""
