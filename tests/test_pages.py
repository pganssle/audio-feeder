"""Tests for audio_feeder.pages"""

import typing

import pytest

from audio_feeder import pages


@pytest.mark.parametrize(
    "args, expected_per_page",
    [
        ({}, 25),
        ({"perPage": "10"}, 10),
        ({"perPage": "not-a-number"}, 25),
    ],
)
def test_sortable_args_per_page(
    args: typing.Mapping[str, str], expected_per_page: int
) -> None:
    assert pages.get_sortable_args(args)["perPage"] == expected_per_page
