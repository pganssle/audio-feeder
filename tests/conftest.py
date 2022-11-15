import contextlib
import enum
import importlib.resources
import logging
import os
import pathlib
import shutil
import subprocess
import tempfile
import typing

import pytest

import audio_feeder.config
from audio_feeder import cache_utils, file_probe


def copy_data_structure(dest: pathlib.Path):
    to_copy: typing.List[
        typing.Tuple[importlib.resources.abc.Traversable, pathlib.Path]
    ] = []
    nodes = []
    nodes.append((dest, importlib.resources.files("audio_feeder.data"), True))
    while nodes:
        parent, node, is_root = nodes.pop()
        if is_root:
            parent_dir = parent
        else:
            parent_dir = parent / node.name
        for child in node.iterdir():
            if child.is_dir():
                nodes.append((parent_dir, child, False))
            elif child.is_file():
                child_dest = parent_dir / child.name
                if child_dest.suffix not in (".py", ".pyc", ".pyo", ".pyi"):
                    to_copy.append((child, child_dest))

        for source, destination in to_copy:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())


@pytest.fixture(scope="session", autouse=True)
def configure_logging() -> None:
    logging.basicConfig(level=logging.DEBUG)


@pytest.fixture(scope="session", autouse=True)
def config_defaults(tmp_path_factory) -> typing.Iterator[pathlib.Path]:
    config_dir = tmp_path_factory.mktemp("config")
    templates_loc = config_dir / "templates"
    static_loc = config_dir / "static"
    (config_dir / "database").mkdir()

    copy_data_structure(config_dir)
    test_config_file = pathlib.Path(__file__).parent / "data/config.yml"
    config_loc = config_dir / "config.yml"
    shutil.copy(test_config_file, config_loc)

    os.environ["AF_CONFIG_DIR"] = os.environ.get(
        "AF_CONFIG_DIR", os.fspath(config_loc.parent)
    )
    yield config_loc


_OptPath = typing.TypeVar("_OptPath", bound=typing.Optional[pathlib.Path])


@contextlib.contextmanager
def change_config_loc(new_config_loc: _OptPath = None) -> typing.Iterator[_OptPath]:
    class SentinelEnum(enum.Enum):
        Sentinel = enum.auto

    old_config_dir: typing.Union[
        str, typing.Literal[SentinelEnum.Sentinel]
    ] = os.environ.get("AF_CONFIG_DIR", SentinelEnum.Sentinel)
    try:
        if new_config_loc is None:
            del os.environ["AF_CONFIG_DIR"]
        else:
            os.environ["AF_CONFIG_DIR"] = os.fspath(new_config_loc)  # type: ignore[arg-type]

        yield new_config_loc  # type: ignore[misc]
    finally:
        if old_config_dir is SentinelEnum.Sentinel:
            del os.environ["AF_CONFIG_DIR"]
        else:
            os.environ["AF_CONFIG_DIR"] = old_config_dir


@pytest.fixture
def default_config_locs(config_defaults: pathlib.Path) -> None:
    with change_config_loc(None):
        yield


@pytest.fixture
def testgen_config(
    config_defaults: pathlib.Path, tmp_path: pathlib.Path
) -> typing.Iterator[pathlib.Path]:
    cache_utils.clear_caches()
    config_loc = tmp_path / "config"
    shutil.copytree(config_defaults.parent, config_loc)
    shutil.copytree(
        pathlib.Path(__file__).parent / "data/example_media",
        config_loc / "static/media",
    )

    (config_loc / "static/images").mkdir()
    (config_loc / "static/images/entry_cover_cache").mkdir()
    (config_loc / "static/media_cache").mkdir()

    with change_config_loc(config_loc):
        yield config_loc
