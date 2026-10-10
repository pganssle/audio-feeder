"""Filtering the list of entries."""

import collections
from collections.abc import Iterable, Mapping, Sequence
from pathlib import PurePosixPath
from typing import Self

import attrs

from . import object_handler as oh


class InvalidFilter(ValueError):
    """Raised when a filter parameter can't be parsed."""


def parse_folder(value: str | None) -> PurePosixPath | None:
    """Parse a folder from a query parameter.

    Folders are relative to the media directory, with ``/`` as the separator.
    Leading, trailing and repeated slashes are ignored, and the empty string
    refers to the root, which is returned as ``None``.

    :raises InvalidFilter:
        If the folder contains a ``..`` component.
    """
    if value is None:
        return None

    parts = [part for part in value.split("/") if part not in ("", ".")]
    if ".." in parts:
        raise InvalidFilter(f"Folder may not contain '..': {value!r}")

    return PurePosixPath(*parts) if parts else None


def entry_location(entry: oh.Entry) -> PurePosixPath:
    """The entry's location relative to the media directory."""
    return PurePosixPath(entry.path.as_posix())


def in_folder(entry: oh.Entry, folder: PurePosixPath | None) -> bool:
    """Whether ``entry`` is somewhere below ``folder`` (``None`` is the root)."""
    return folder is None or folder in entry_location(entry).parents


@attrs.frozen
class FolderCount:
    folder: PurePosixPath
    count: int

    @property
    def name(self) -> str:
        return self.folder.name


def subfolders(
    entries: Iterable[oh.Entry], folder: PurePosixPath | None
) -> Sequence[FolderCount]:
    """The folders immediately below ``folder``, with the number of entries in each.

    Chains of folders that contain nothing but a single subfolder are
    collapsed, so that e.g. if every entry is somewhere below ``audiobooks/``,
    the subfolders of the root are the subfolders of ``audiobooks/``.

    Only folders that contain entries (at any depth) are included, sorted by
    name.
    """
    locations = [entry_location(entry) for entry in entries if in_folder(entry, folder)]

    while True:
        depth = len(folder.parts) if folder is not None else 0
        counts: collections.Counter[PurePosixPath] = collections.Counter()
        entries_here = False
        for location in locations:
            # An entry's location is its own directory, so it is directly in
            # `folder` if its parent is `folder`.
            if len(location.parts) <= depth + 1:
                entries_here = True
            else:
                counts[PurePosixPath(*location.parts[: depth + 1])] += 1

        if len(counts) == 1 and not entries_here:
            ((folder, _),) = counts.items()
            continue

        return [
            FolderCount(subfolder, count)
            for subfolder, count in sorted(counts.items(), key=lambda kv: kv[0])
        ]


def breadcrumbs(folder: PurePosixPath | None) -> Sequence[PurePosixPath]:
    """The chain of folders from the top level down to ``folder``."""
    if folder is None:
        return []

    return [*reversed(folder.parents[:-1]), folder]


@attrs.frozen
class EntryFilter:
    """A set of criteria for selecting entries to display."""

    folder: PurePosixPath | None = None

    @classmethod
    def from_args(cls, args: Mapping[str, str]) -> Self:
        """Create a filter from query parameters.

        :raises InvalidFilter:
            If any of the parameters are invalid.
        """
        return cls(folder=parse_folder(args.get("folder", None)))

    def to_params(self) -> Mapping[str, str]:
        """The query parameters that represent this filter."""
        params = {}
        if self.folder is not None:
            params["folder"] = self.folder.as_posix()
        return params

    def matches(self, entry: oh.Entry) -> bool:
        return in_folder(entry, self.folder)

    def apply(self, entries: Iterable[oh.Entry]) -> Sequence[oh.Entry]:
        return [entry for entry in entries if self.matches(entry)]
