"""Tests for audio_feeder.cli"""

import pathlib
from collections.abc import Sequence

import pytest
from click import testing

from audio_feeder import cli

from . import test_updater


@pytest.mark.parametrize(
    "args, expected",
    [
        # With no PATH, the configured directories are updated
        ((), test_updater.FICTION_PATHS),
        (("-t", "books"), test_updater.FICTION_PATHS),
        # An explicit PATH is still supported
        (("audiobooks/Nonfiction",), test_updater.NONFICTION_PATHS),
        (("--content-type", "books", "."), test_updater.ALL_PATHS),
    ],
)
def test_update(
    testgen_config: pathlib.Path,
    args: Sequence[str],
    expected: frozenset[pathlib.Path],
) -> None:
    test_updater.set_content_paths(testgen_config, "{books: audiobooks/Fiction}")
    with test_updater.patch_book_updater():
        result = testing.CliRunner().invoke(cli.cli, ["update", *args])

    assert result.exit_code == 0, result.output
    assert test_updater.entry_paths() == sorted(expected)


def test_update_unknown_content_type(testgen_config: pathlib.Path) -> None:
    result = testing.CliRunner().invoke(cli.cli, ["update", "-t", "courses"])

    assert isinstance(result.exception, ValueError)
    assert "Unknown content type: courses" in str(result.exception)
