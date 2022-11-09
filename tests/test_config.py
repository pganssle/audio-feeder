import contextlib
import enum
import os
import pathlib
import typing

import pytest

from audio_feeder import config


@pytest.fixture
def default_config_locs(config_defaults: pathlib.Path) -> None:
    class SentinelEnum(enum.Enum):
        Sentinel = enum.auto

    old_config_dir: typing.Union[
        str, typing.Literal[SentinelEnum.Sentinel]
    ] = os.environ.get("AF_CONFIG_DIR", SentinelEnum.Sentinel)
    if old_config_dir is not SentinelEnum.Sentinel:
        del os.environ["AF_CONFIG_DIR"]
        yield
        os.environ["AF_CONFIG_DIR"] = old_config_dir


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
        conf = config.Configuration(config_defaults, bad_kwargs="howdy")


def test_config_from_file(tmp_path: pathlib.Path) -> None:
    with pytest.raises(IOError, match=f"{tmp_path}"):
        conf = config.Configuration.from_file(tmp_path / "config.yml")


def test_config_to_file(tmp_path: pathlib.Path) -> None:
    config_loc = tmp_path / "config.yml"
    conf = config.Configuration(config_loc, base_host="mydomain.pizza")

    assert not config_loc.exists()

    conf.to_file(config_loc)

    assert config_loc.exists()

    conf_rt = config.Configuration.from_file(config_loc)

    assert conf_rt.base_host == conf.base_host
