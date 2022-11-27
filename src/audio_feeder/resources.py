"""Modules for handling package data resources."""
import functools
from importlib import resources
from importlib.abc import Traversable
from pathlib import Path


def _copy_resource(resource: Traversable, target_dir: Path) -> None:
    if resource.is_file():
        if not target_dir.exists():
            target_dir.mkdir(parents=True)

        target_loc = target_dir / resource.name
        target_loc.write_bytes(resource.read_bytes())
    else:
        for child in resource.iterdir():
            if (
                child.name.endswith(".py")
                or child.name.endswith(".pyc")
                or child.name == "__pycache__"
            ):
                continue
            if child.is_dir():
                _copy_resource(child, target_dir / child.name)
            else:
                _copy_resource(child, target_dir)


@functools.singledispatch
def copy_resource(resource: Traversable, target_dir: Path) -> None:
    """Copies a resource from the package data to a target path.

    This will not copy any `.py` files or __pycache__ files, and it recursively
    copies entire directory trees.

    :param resource:
        Either a string representing the resource in the package (e.g.
        "audio_feeder.data.site") or an `importlib.abc.Traversable` (e.g.
        resources.files("audio_feeder.data.site").

    :param target_dir:
        A directory to copy the data into. This will be the parent directory
        of whatever you copy, even if `resource` represents a directory.
    """
    _copy_resource(resource, target_dir)


@copy_resource.register
def _(resource: str, target_dir: Path) -> None:
    traversable = resources.files(resource)
    copy_resource(traversable, target_dir)
