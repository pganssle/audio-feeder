import datetime
import os
import pathlib
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from audio_feeder import config


def test_config_dirs_pwd(default_config_locs, tmp_path):
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert tmp_path in config.config_dirs(with_pwd=True)
    finally:
        os.chdir(cwd)


def test_config_dirs_no_pwd(default_config_locs: None, tmp_path: pathlib.Path):
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert tmp_path not in config.config_dirs(with_pwd=False)
    finally:
        os.chdir(cwd)


def test_extra_kwargs(config_defaults: pathlib.Path) -> None:
    with pytest.raises(TypeError, match="bad_kwargs"):
        config.Configuration(config_defaults, bad_kwargs="howdy")


def test_config_from_file(tmp_path: pathlib.Path) -> None:
    with pytest.raises(IOError, match=f"{tmp_path}"):
        config.Configuration.from_file(tmp_path / "config.yml")


def test_config_to_file(tmp_path: pathlib.Path) -> None:
    config_loc = tmp_path / "config.yml"
    conf = config.Configuration(config_loc, base_host="mydomain.pizza")

    assert not config_loc.exists()

    conf.to_file(config_loc)

    assert config_loc.exists()

    conf_rt = config.Configuration.from_file(config_loc)

    assert conf_rt.base_host == conf.base_host


def test_config_url_no_port(tmp_path: pathlib.Path) -> None:
    config_loc = tmp_path / "config.yml"
    conf = config.Configuration(
        config_loc, base_protocol="https", base_host="mydomain.pizza", base_port=None
    )

    assert conf.base_url == "https://mydomain.pizza"
    assert conf.static_media_url == "https://mydomain.pizza/static"


def test_config_bad_replacement(tmp_path: pathlib.Path) -> None:
    config_loc = tmp_path / "config.yml"
    with pytest.raises(ValueError, match="BADLOC"):
        config.Configuration(
            config_loc,
            database_loc=config.TemplatePath("{{BADLOC}}", "database/db.sqlite"),
        )


def test_metadata_retry_from_file(tmp_path: pathlib.Path) -> None:
    config_loc = tmp_path / "config.yml"
    config_loc.write_text(
        "metadata_retry:\n"
        "  google_books:\n"
        "    quota_cooldown: {hours: 6}\n"
        "    request_timeout: 10\n"
        "    request_retries: 5\n"
    )
    conf = config.Configuration.from_file(config_loc)

    assert conf.metadata_retry == {
        "google_books": config.MetadataRetryConfig(
            quota_cooldown=datetime.timedelta(hours=6),
            request_timeout=datetime.timedelta(seconds=10),
            request_retries=5,
        )
    }

    # Settings that aren't specified keep their defaults
    defaults = config.MetadataRetryConfig()
    google_books = conf.metadata_retry["google_books"]
    assert google_books.not_found_retry_base == defaults.not_found_retry_base

    # The settings survive a round trip through the file
    round_trip_loc = tmp_path / "round_trip.yml"
    conf.to_file(round_trip_loc)
    round_trip = config.Configuration.from_file(round_trip_loc)
    assert round_trip.metadata_retry == conf.metadata_retry


def test_content_paths_default(tmp_path: pathlib.Path) -> None:
    # By default, the whole media directory contains books
    conf = config.Configuration(tmp_path / "config.yml")
    assert conf.content_paths == {"books": (pathlib.Path("."),)}


def test_content_paths_written_to_file(tmp_path: pathlib.Path) -> None:
    config_loc = tmp_path / "config.yml"
    config.Configuration(config_loc).to_file(config_loc)

    assert "content_paths:\n  books:\n  - .\n" in config_loc.read_text()


@pytest.mark.parametrize(
    "yaml_value, expected",
    [
        ("{books: audiobooks}", {"books": (pathlib.Path("audiobooks"),)}),
        ("{books: [audiobooks]}", {"books": (pathlib.Path("audiobooks"),)}),
        (
            "{books: [audiobooks, /mnt/books], courses: courses}",
            {
                "books": (pathlib.Path("audiobooks"), pathlib.Path("/mnt/books")),
                "courses": (pathlib.Path("courses"),),
            },
        ),
        ("{books: []}", {"books": ()}),
        ("{books: null}", {"books": ()}),
        ("{}", {}),
    ],
)
def test_content_paths_from_file(
    tmp_path: pathlib.Path,
    yaml_value: str,
    expected: Mapping[str, Sequence[pathlib.Path]],
) -> None:
    config_loc = tmp_path / "config.yml"
    config_loc.write_text(f"content_paths: {yaml_value}\n")
    conf = config.Configuration.from_file(config_loc)

    assert conf.content_paths == expected

    # The setting survives a round trip through the file
    round_trip_loc = tmp_path / "round_trip.yml"
    conf.to_file(round_trip_loc)
    round_trip = config.Configuration.from_file(round_trip_loc)
    assert round_trip.content_paths == expected


@pytest.mark.parametrize(
    "value",
    [
        {"books": "audiobooks"},
        {"books": pathlib.Path("audiobooks")},
        {"books": ["audiobooks"]},
        {"books": (pathlib.Path("audiobooks"),)},
    ],
)
def test_content_paths_from_python(
    tmp_path: pathlib.Path, value: Mapping[str, Any]
) -> None:
    conf = config.Configuration(tmp_path / "config.yml", content_paths=value)
    assert conf.content_paths == {"books": (pathlib.Path("audiobooks"),)}
