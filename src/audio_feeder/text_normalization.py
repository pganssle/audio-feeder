"""Normalizing text for comparisons and sorting."""

import re
import unicodedata
from typing import Final, TypeAlias

_DIGITS: Final = re.compile(r"(\d+)")

SortKey: TypeAlias = tuple[tuple[str | int, ...], str]


def normalize(text: str) -> str:
    """Normalize text for case- and accent-insensitive comparison.

    The text is case folded and compatibility-decomposed, and any combining
    characters (such as accents) are removed, so "Miéville" and "MIEVILLE"
    both normalize to "mieville".
    """
    # This is compatibility caseless matching (Unicode D146), which case folds
    # again after decomposing, since decomposition can produce characters that
    # case fold (e.g. "𝕬" decomposes to "A"). Combining characters are then
    # removed to ignore accents.
    folded = unicodedata.normalize("NFD", text).casefold()
    folded = unicodedata.normalize("NFKD", folded).casefold()
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def sort_key(text: str) -> SortKey:
    """A key for sorting text the way a person would expect.

    Text is compared without regard to case or accents, and runs of digits are
    compared by their numeric value, so "Book 2" sorts before "Book 10". Text
    that compares equal under those rules is ordered by the original string,
    so the key is only equal for identical strings.
    """
    # Splitting on a capturing group always gives text at the even indices and
    # digits at the odd ones, so corresponding chunks of any two keys have the
    # same type and can be compared.
    chunks = _DIGITS.split(normalize(text))
    natural = tuple(int(chunk) if i % 2 else chunk for i, chunk in enumerate(chunks))
    return (natural, text)
