"""Modules for handling package data resources."""
import hashlib
import importlib.resources
import os
from importlib.abc import Traversable
from pathlib import Path
from typing import Callable, Iterable, Optional, Protocol, Union


class _Comparable(Protocol):
    def read_bytes(self) -> bytes:  # pragma: nocover
        ...

    def is_dir(self) -> bool:  # pragma: nocover
        ...

    def is_file(self) -> bool:  # pragma: nocover
        ...


_CompareFunc = Callable[[_Comparable, Path], bool]


def _copy_resource(
    resource: Traversable, target_dir: Path, copy_if: Optional[_CompareFunc] = None
) -> None:
    target_loc = target_dir / resource.name
    if copy_if is not None:
        if not copy_if(resource, target_loc):
            return

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
                _copy_resource(child, target_dir / child.name, copy_if=copy_if)
            else:
                _copy_resource(child, target_dir, copy_if=copy_if)


def _resolve_resource(resource: Union[str, Traversable]) -> Traversable:
    if isinstance(resource, str):
        return importlib.resources.files(resource)
    return resource


def copy_resource(resource: Union[str, Traversable], target_dir: Path) -> None:
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
    resource = _resolve_resource(resource)
    _copy_resource(resource, target_dir)


def _copy_if_hash_mismatch(resource: _Comparable, target: Path) -> bool:
    if resource.is_dir() or not target.exists():
        return True

    if isinstance(resource, os.PathLike):
        if os.path.getsize(resource) != os.path.getsize(target):
            return True

    resource_hash = hashlib.sha256(resource.read_bytes()).digest()
    existing_hash = hashlib.sha256(target.read_bytes()).digest()

    return resource_hash != existing_hash


def update_resource(resource: Union[str, Traversable], target_dir: Path) -> None:
    """Update a resource on disk if its contents have changed.

    This is equivalent to copy_resource, but if the resource already exists
    on disk and has the same contents, no copy will occur.
    """
    resource = _resolve_resource(resource)
    _copy_resource(resource, target_dir, copy_if=_copy_if_hash_mismatch)


def get_text_resource(package: str, resource: str) -> str:
    """Retrieve the text of a given text resource."""
    return importlib.resources.read_text(package, resource)


def get_children(resource: Union[str, Traversable]) -> Iterable[Traversable]:
    """Retrieve a list of resources nested under the specified `resource`."""
    resource = _resolve_resource(resource)
    yield from resource.iterdir()
