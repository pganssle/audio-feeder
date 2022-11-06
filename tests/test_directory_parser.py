import itertools
import typing

import hypothesis
import pytest
from hypothesis import strategies as st

from audio_feeder import directory_parser as dp

###
# Test AudiobookLoader


def mk_audio_info(authors, title, series=(None, None)):
    return dict(authors=authors, title=title, series=series)


audio_parser_test_data = [
    (
        "Nonfiction/History/Adam Cohen - Imbeciles",
        mk_audio_info(["Adam Cohen"], "Imbeciles"),
    ),
    (
        "Fiction/Science Fiction/Lois McMaster Bujold - [Vorkosigan Saga 01] - Falling Free",
        mk_audio_info(
            ["Lois McMaster Bujold"], "Falling Free", series=("Vorkosigan Saga", 1)
        ),
    ),
    (
        "Nonfiction/Sports/Jeff Benedict and Armen Keteyian - The System",
        mk_audio_info(["Jeff Benedict", "Armen Keteyian"], "The System"),
    ),
    (
        "Fiction/Children/Antoine de Saint-Exupéry - The Little Prince",
        mk_audio_info(["Antoine de Saint-Exupéry"], "The Little Prince"),
    ),
    (
        "Nonfiction/Sports/Mark Fainaru-Wada and Steve Fainaru - League of Denial",
        mk_audio_info(["Mark Fainaru-Wada", "Steve Fainaru"], "League of Denial"),
    ),
    (
        "Fiction/Historical Fiction/James Clavell - [Asian Saga 01] - Shogun",
        mk_audio_info(["James Clavell"], "Shogun", series=("Asian Saga", 1)),
    ),
    (
        "Nonfiction/Chemistry/Douglas Skoog, James Holler and Stanley Crouch - "
        "Principles of Instrumental Analysis",
        mk_audio_info(
            ["Douglas Skoog", "James Holler", "Stanley Crouch"],
            "Principles of Instrumental Analysis",
        ),
    ),
]


@pytest.mark.parametrize("path,exp_audio_info", audio_parser_test_data)
def test_ab_loader_audio_info(path, exp_audio_info):
    audio_info = dp.AudiobookLoader.parse_audio_info(path)

    assert audio_info == exp_audio_info, audio_info


@pytest.mark.parametrize(
    "sorted_str_list",
    [
        ("abc123", "abc234", "abc1234"),
        ("abc",),
        ("123", "abc"),
        ("123abc56", "123abc456", "123abc456z", "abc123456"),
        ("", "456"),
    ],
)
def test_natural_sort(sorted_str_list: typing.Sequence[str], subtests) -> None:
    """Test that all permutations of already sorted strings remain storted."""
    for permutation in itertools.permutations(sorted_str_list):
        with subtests.test(permutation=permutation):
            assert list(
                sorted(permutation, key=dp.BaseAudioLoader.natural_sort_key)
            ) == list(sorted_str_list)


@hypothesis.given(strs=st.lists(st.text(), max_size=100))
def test_natural_sort_noerror(strs: typing.Sequence[str]) -> None:
    """Ensure that there is no error sorting randomly drawn strings."""
    sorted_strs = sorted(strs, key=dp.BaseAudioLoader.natural_sort_key)
    assert len(strs) == len(sorted_strs)
