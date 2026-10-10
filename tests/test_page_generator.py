"""Tests for audio_feeder.page_generator"""

import pathlib

import pytest

from audio_feeder import page_generator as pg
from audio_feeder import resolver


def test_load_type_without_templates(testgen_config: pathlib.Path) -> None:
    renderer = pg.EntryRenderer(resolver.get_resolver())
    (renderer.entry_templates_loc / "empty_type").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="empty_type"):
        renderer.load_type("empty_type")


@pytest.mark.parametrize(
    "params, expected_url",
    [
        ({"page": 2, "perPage": 25}, "/books?page=2&perPage=25"),
        (
            {"folder": "Fiction/Science & Nature"},
            "/books?folder=Fiction%2FScience+%26+Nature",
        ),
        ({"q": "a=b?c#d"}, "/books?q=a%3Db%3Fc%23d"),
    ],
)
def test_nav_item_url_encodes_params(
    params: dict[str, object], expected_url: str
) -> None:
    assert pg.NavItem("/books", "1", params=params).url == expected_url


def test_nav_item_without_params() -> None:
    assert pg.NavItem("/books", "1").url == "/books"
    assert pg.NavItem("/books", "1", params={"page": 2}).display_only().url is None
