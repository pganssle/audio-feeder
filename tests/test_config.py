import os
import pathlib

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
