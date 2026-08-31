"""Reading a customer's name off a questionnaire title — carefully.

Customer-provided questionnaires exist from before the engagement model,
and they carry no `customer_name` because there was no column to put one
in. Their titles usually contain the customer anyway: somebody typed
"Agora Origin cusotmer" when they made it.

That is a suggestion, not a fact. A title is free text; treating it as
identity is how a typo becomes a customer in an audit trail, and how a
questionnaire titled "Do you encrypt customer data at rest?" acquires a
customer called "Do You Encrypt". So this module's job is not to extract
a name — it is to *refuse* to, unless what is left after removing the
questionnaire vocabulary reads like somebody's name.

Nothing here writes anything. A suggestion reaches the database only
when a person confirms it, and `reason` is carried along so the audit
trail records how the name was arrived at rather than just asserting it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

# Words that describe the document rather than the customer. Stripped
# from either end, repeatedly, until only the name is left.
NOISE = frozenset(
    {
        "questionnaire", "questionaire", "quesitonnaire",
        "security", "privacy", "infosec", "cyber",
        "assessment", "review", "audit", "request", "response",
        "form", "survey", "checklist", "intake", "screening",
        "vendor", "supplier", "customer", "client", "buyer",
        "third", "party", "3rd",
        "due", "diligence", "ddq", "dd", "vsq", "sig", "caiq",
        "template", "copy", "draft", "final", "new", "untitled",
        "test", "sample", "example", "imported", "pasted", "sheet",
        "for", "from", "the", "a", "an", "of", "and", "re",
        "v1", "v2", "v3", "q1", "q2", "q3", "q4",
    }
)

# A title that opens with one of these is a question, and a question is
# not a name however much of it survives the trimming.
INTERROGATIVE = frozenset(
    {
        "do", "does", "did", "is", "are", "was", "were", "am",
        "can", "could", "will", "would", "shall", "should", "may", "might",
        "have", "has", "had",
        "how", "what", "which", "who", "whom", "whose",
        "where", "when", "why",
        "please", "describe", "explain", "list", "provide", "confirm",
        "detail", "outline", "state", "specify", "attach", "upload",
    }
)

# Fuzzy matching only for words long enough that a near-miss is far more
# likely to be a typo than a different word. "cusotmer" is a transposed
# "customer"; "acme" is not a near-miss of anything.
_FUZZY_MIN_LENGTH = 7
_FUZZY_RATIO = 0.82

# Past these, the string is prose rather than a name.
MAX_TITLE_WORDS = 12
MAX_NAME_WORDS = 5
MAX_NAME_CHARS = 60
MIN_NAME_CHARS = 2

_WORD = re.compile(r"[^\w&.'-]+", re.UNICODE)


@dataclass(frozen=True)
class CustomerSuggestion:
    """A name a person still has to agree to.

    `reason` travels with it into the confirmation's audit event, so the
    record says the name came from the title rather than presenting it as
    though somebody had always known it.
    """

    name: str
    reason: str


def _words(title: str) -> list[str]:
    return [w for w in _WORD.split(title.strip()) if w]


def _is_noise(word: str) -> bool:
    plain = word.lower().strip(".'-&")
    if not plain:
        return True
    if plain in NOISE:
        return True
    if len(plain) < _FUZZY_MIN_LENGTH:
        return False
    # A long word that is one slip away from questionnaire vocabulary.
    return any(
        len(candidate) >= _FUZZY_MIN_LENGTH
        and SequenceMatcher(None, plain, candidate).ratio() >= _FUZZY_RATIO
        for candidate in NOISE
    )


def _reads_like_a_question(title: str, words: list[str]) -> bool:
    if title.rstrip().endswith("?"):
        return True
    return bool(words) and words[0].lower() in INTERROGATIVE


def reads_like_a_question(title: str | None) -> bool:
    """Is this title one of the questions rather than the document's name?

    "Do you encrypt customer data at rest?" is a line inside a
    questionnaire, not what the questionnaire is called — and a review
    named after it reads as nonsense. The same test the customer
    suggestion already applies, exposed because the screen wants to say
    so before somebody creates another one.

    A flag, never an action. The product can see that a title reads
    oddly; only a person knows what it should say instead.
    """
    raw = (title or "").strip()
    if not raw:
        return False
    return _reads_like_a_question(raw, _words(raw))


def suggest_customer_name(title: str | None) -> CustomerSuggestion | None:
    """The customer this title names, or None if it does not clearly name one.

    None is the ordinary answer, not a failure. It means the product has
    to ask somebody, which is the correct outcome for a record whose
    customer nobody ever recorded.
    """
    raw = (title or "").strip()
    if not raw:
        return None

    words = _words(raw)
    if not words or len(words) > MAX_TITLE_WORDS:
        return None
    if _reads_like_a_question(raw, words):
        return None

    trimmed = list(words)
    while trimmed and _is_noise(trimmed[0]):
        trimmed.pop(0)
    while trimmed and _is_noise(trimmed[-1]):
        trimmed.pop()

    if not trimmed or len(trimmed) > MAX_NAME_WORDS:
        return None
    # Vocabulary left in the middle means the remainder is a phrase, not a
    # name: "Acme data protection questionnaire" should not become
    # "Acme data protection".
    if any(_is_noise(word) for word in trimmed):
        return None

    name = " ".join(trimmed)
    if not (MIN_NAME_CHARS <= len(name) <= MAX_NAME_CHARS):
        return None
    if not any(character.isalpha() for character in name):
        return None

    removed = len(words) - len(trimmed)
    reason = (
        f'Suggested from the questionnaire title "{raw}"'
        + (f" with {removed} descriptive word{'' if removed == 1 else 's'} removed."
           if removed
           else ".")
    )
    return CustomerSuggestion(name=name, reason=reason)


__all__ = [
    "INTERROGATIVE",
    "reads_like_a_question",
    "MAX_NAME_WORDS",
    "MAX_TITLE_WORDS",
    "NOISE",
    "CustomerSuggestion",
    "suggest_customer_name",
]
