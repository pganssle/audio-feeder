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
