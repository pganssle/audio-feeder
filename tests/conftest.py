import importlib.resources
import pathlib
import shutil
import typing

import pytest

import audio_feeder.config


def copy_data_structure(dest: pathlib.Path):
    to_copy: typing.List[
        typing.Tuple[importlib.resources.abc.Traversable, pathlib.Path]
    ] = []
    nodes = []
    nodes.append((dest, importlib.resources.files("audio_feeder.data")))
    while nodes:
        parent, node = nodes.pop()
        parent_dir = parent / node.name
        for child in node.iterdir():
            if child.is_dir():
                nodes.append((parent_dir, child))
            elif child.is_file():
                dest = parent_dir / child.name
                if dest.suffix not in (".py", ".pyc", ".pyo", ".pyi"):
                    to_copy.append((child, dest))

        for source, destination in to_copy:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())


@pytest.fixture(scope="session", autouse=True)
def config_defaults(tmp_path_factory):
    config_dir = tmp_path_factory.mktemp("config")
    templates_loc = config_dir / "templates"
    static_loc = config_dir / "static"

    copy_data_structure(config_dir)
    test_config_file = pathlib.Path(__file__).parent / "data/config.yml"
    config_loc = config_dir / "config.yml"
    shutil.copy(test_config_file, config_loc)

    audio_feeder.config.init_config(config_loc=config_loc)
