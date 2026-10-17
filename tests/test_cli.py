"""Tests for audio_feeder.cli"""

import pathlib
from collections.abc import Iterator, Sequence

import pytest
from click import testing

from audio_feeder import cache_utils, cli
from audio_feeder import config as af_config

from . import conftest, test_updater


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


@pytest.fixture
def install_dir(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[pathlib.Path]:
    """An empty directory to install into, which is also the working directory."""
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    monkeypatch.chdir(install_dir)
    cache_utils.clear_caches()
    with conftest.change_config_loc(install_dir):
        yield install_dir
    cache_utils.clear_caches()


@pytest.mark.parametrize(
    "existing_config, site_images_loc",
    [
        (None, "images/site-images"),
        # Configurations written by `install` contain the default explicitly.
        ("site_images_loc: images/site-images\n", "images/site-images"),
        ("site_images_loc: site-images\n", "site-images"),
        ("site_images_loc: my/images\n", "my/images"),
    ],
)
def test_install_default_cover(
    install_dir: pathlib.Path, existing_config: str | None, site_images_loc: str
) -> None:
    config_loc = install_dir / "config.yml"
    if existing_config is not None:
        config_loc.write_text(existing_config)

    result = testing.CliRunner().invoke(
        cli.cli, ["install", "--config-dir", str(install_dir)]
    )
    assert result.exit_code == 0, result.output

    cache_utils.clear_caches()
    configuration = af_config.init_config(config_loc, config_loc_must_exist=True)
    assert configuration.site_images_loc == site_images_loc

    # The page links to the default cover relative to the static media path
    site_images = configuration.static_media_path / site_images_loc
    assert site_images == install_dir / "static" / site_images_loc
    assert (site_images / "default_cover.svg").is_file()
