"""Tests for audio_feeder.cli"""

import os
import pathlib
from collections.abc import Iterator, Sequence
from typing import Final

import pytest
import yaml
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


# The directories that `install` creates with the default configuration,
# relative to the configuration directory.
INSTALLED_DIRECTORIES: Final[Sequence[pathlib.Path]] = tuple(
    map(
        pathlib.Path,
        (
            "database",
            "static",
            "static/images/entry_cover_cache",
            "static/images/qr_cache",
            "static/media_cache",
        ),
    )
)


@pytest.fixture
def install_cwd(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[pathlib.Path]:
    """An empty working directory to run `install` from.

    No configuration location is set in the environment, so the default
    configuration search would find the working directory first.
    """
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("AF_CONFIG_DIR", raising=False)
    monkeypatch.delenv("AUDIO_FEEDER_CONFIG", raising=False)
    cache_utils.clear_caches()
    yield cwd
    cache_utils.clear_caches()


def install(*args: str) -> None:
    result = testing.CliRunner().invoke(cli.cli, ["install", *args])
    assert result.exit_code == 0, result.output


def assert_installed(config_loc: pathlib.Path) -> None:
    config_dir = config_loc.parent
    assert config_loc.is_file()
    for directory in INSTALLED_DIRECTORIES:
        assert (config_dir / directory).is_dir(), directory

    installed_config = af_config.Configuration.from_file(config_loc)
    assert installed_config.static_media_path == config_dir / "static"
    assert installed_config.database_loc == config_dir / "database/db.sqlite"


@pytest.mark.parametrize("exists", [True, False])
@pytest.mark.parametrize("config_dir_name", ["server", "some/nested/server"])
def test_install_config_dir(
    install_cwd: pathlib.Path,
    tmp_path: pathlib.Path,
    config_dir_name: str,
    exists: bool,
) -> None:
    config_dir = tmp_path / config_dir_name
    if exists:
        config_dir.mkdir(parents=True)

    install("--config-dir", str(config_dir))

    assert_installed(config_dir / "config.yml")
    # Nothing is created in the working directory
    assert list(install_cwd.iterdir()) == []


def test_install_relative_config_dir(install_cwd: pathlib.Path) -> None:
    install("--config-dir", "server")

    assert_installed(install_cwd / "server/config.yml")
    assert list(install_cwd.iterdir()) == [install_cwd / "server"]


def test_install_config_name(install_cwd: pathlib.Path, tmp_path: pathlib.Path) -> None:
    config_dir = tmp_path / "server"
    install("--config-dir", str(config_dir), "--config-name", "server.yml")

    assert_installed(config_dir / "server.yml")
    assert not (config_dir / "config.yml").exists()
    assert list(install_cwd.iterdir()) == []


def test_install_existing(install_cwd: pathlib.Path, tmp_path: pathlib.Path) -> None:
    config_dir = tmp_path / "server"
    config_loc = config_dir / "config.yml"
    install("--config-dir", str(config_dir))

    # Settings in the existing configuration file are kept
    settings = yaml.safe_load(config_loc.read_text())
    settings["base_host"] = "audiobooks.example"
    config_loc.write_text(yaml.safe_dump(settings))
    cache_utils.clear_caches()

    install("--config-dir", str(config_dir))

    assert_installed(config_loc)
    assert af_config.Configuration.from_file(config_loc).base_host == (
        "audiobooks.example"
    )
    assert list(install_cwd.iterdir()) == []


def test_find_missing_books_without_author(
    testgen_config: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    # Books in directories with no author in the name are listed with no author
    media_dir = testgen_config / "static/media"
    found = test_updater.add_unparseable_book(media_dir, test_updater.UNPARSEABLE_FOUND)
    not_found = test_updater.add_unparseable_book(
        media_dir, test_updater.UNPARSEABLE_NOT_FOUND
    )
    with test_updater.patch_book_updater(test_updater.unparseable_book_responses()):
        result = testing.CliRunner().invoke(cli.cli, ["update", "."])
    assert result.exit_code == 0, result.output

    output = tmp_path / "missing.yml"
    result = testing.CliRunner().invoke(
        cli.cli, ["find-missing-books", "load", "-yo", "-o", os.fspath(output)]
    )
    assert result.exit_code == 0, result.output

    missing = {
        book[2]["title"]: book[1]["authors"]
        for book in yaml.safe_load(output.read_text())
    }
    assert missing[not_found.name] == []
    assert found.name not in missing
