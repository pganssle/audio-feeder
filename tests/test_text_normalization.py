"""Tests for audio_feeder.text_normalization"""

from collections.abc import Sequence

import pytest
from hypothesis import given
from hypothesis import strategies as st

from audio_feeder import text_normalization as tn


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", ""),
        ("China Miéville", "china mieville"),
        ("MIÉVILLE", "mieville"),
        ("Straße", "strasse"),
        ("Ｆｕｌｌｗｉｄｔｈ", "fullwidth"),
        ("Brontë", "bronte"),
    ],
)
def test_normalize(text: str, expected: str) -> None:
    assert tn.normalize(text) == expected


@pytest.mark.parametrize(
    "expected",
    [
        pytest.param(("Miéville, China", "Mitnick, Kevin"), id="accents"),
        pytest.param(("Mitnick, Kevin", "van der Whatever", "Zola"), id="case"),
        pytest.param(("Book 2", "Book 10", "Book 100"), id="numbers"),
        pytest.param(("Book", "Book 1", "Book 1a", "Book 2"), id="number-suffix"),
        pytest.param(("1984", "Brave New World"), id="leading-number"),
        pytest.param(("", "a"), id="empty"),
        # Equal after normalization: the original string breaks the tie
        pytest.param(("MIEVILLE", "Mieville", "Miéville", "mieville"), id="tie"),
        pytest.param(("Book 02", "Book 2"), id="tie-numbers"),
    ],
)
def test_sort_key_order(expected: Sequence[str]) -> None:
    assert sorted(reversed(expected), key=tn.sort_key) == list(expected)


@given(st.text(), st.text())
def test_sort_key_total_order(a: str, b: str) -> None:
    # Comparisons never raise, and keys are only equal for equal strings
    key_a, key_b = tn.sort_key(a), tn.sort_key(b)
    assert (key_a == key_b) == (a == b)
    assert (key_a < key_b) != (key_b <= key_a)


@given(st.text(), st.text())
def test_sort_key_ignores_case_and_accents(a: str, b: str) -> None:
    # Strings that are equivalent ignoring case and accents are ordered by the
    # original text
    key_a, key_b = tn.sort_key(a), tn.sort_key(b)
    if tn.normalize(a) == tn.normalize(b):
        assert (key_a < key_b) == (a < b)


@given(
    st.text(alphabet=st.characters(categories=["L"])),
    st.integers(min_value=0),
    st.integers(min_value=0),
)
def test_sort_key_numbers_numeric(prefix: str, m: int, n: int) -> None:
    key_m = tn.sort_key(f"{prefix} {m}")
    key_n = tn.sort_key(f"{prefix} {n}")
    assert (key_m < key_n) == (m < n)


@given(st.text())
def test_normalize_idempotent(text: str) -> None:
    normalized = tn.normalize(text)
    assert tn.normalize(normalized) == normalized
