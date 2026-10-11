"""Filtering the list of entries."""

import collections
import datetime
import enum
import unicodedata
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import PurePosixPath
from typing import Protocol, Self

import attrs

from . import object_handler as oh
from ._db_types import ID


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


def parse_date(value: str | None) -> datetime.date | None:
    """Parse a date from a query parameter in ``YYYY-MM-DD`` format.

    :raises InvalidFilter:
        If the date can't be parsed.
    """
    if value is None or not value.strip():
        return None

    try:
        return datetime.date.fromisoformat(value.strip())
    except ValueError as e:
        raise InvalidFilter(f"Invalid date: {value!r}") from e


def _parse_text(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _normalize(text: str) -> str:
    """Normalize text for case- and accent-insensitive comparison."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


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


class QueryArgs(Protocol):
    """Query parameters, where a parameter may be given more than once."""

    def get(self, key: str, /) -> str | None: ...

    def getlist(self, key: str) -> list[str]: ...


class TagMatch(enum.StrEnum):
    """How a book's tags are matched against the included tags."""

    ANY = "any"
    """The book has at least one of the included tags."""

    ALL = "all"
    """The book has every included tag."""


def _folders(values: Iterable[PurePosixPath]) -> tuple[PurePosixPath, ...]:
    return tuple(sorted(set(values)))


def _tags(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value.casefold() for value in values}))


@attrs.frozen
class EntryFilter:
    """A set of criteria for selecting entries to display.

    An entry must be in at least one of ``folders`` (if there are any) and
    in none of ``not_folders``. Its book must have any or all of ``tags``
    (depending on ``tag_match``) and none of ``not_tags``.
    """

    folders: tuple[PurePosixPath, ...] = attrs.field(default=(), converter=_folders)
    not_folders: tuple[PurePosixPath, ...] = attrs.field(default=(), converter=_folders)
    tags: tuple[str, ...] = attrs.field(default=(), converter=_tags)
    not_tags: tuple[str, ...] = attrs.field(default=(), converter=_tags)
    tag_match: TagMatch = attrs.field(default=TagMatch.ANY, converter=TagMatch)
    language: str | None = None
    author: str | None = None
    added_since: datetime.date | None = None
    added_before: datetime.date | None = None

    @classmethod
    def from_args(cls, args: QueryArgs) -> Self:
        """Create a filter from query parameters.

        Empty parameters are ignored, as are empty values of the parameters
        that can be repeated.

        :raises InvalidFilter:
            If any of the parameters are invalid.
        """

        def folders(key: str) -> Iterator[PurePosixPath]:
            for value in args.getlist(key):
                if (folder := parse_folder(value)) is not None:
                    yield folder

        def texts(key: str) -> Iterator[str]:
            for value in args.getlist(key):
                if (text := _parse_text(value)) is not None:
                    yield text

        tag_match_arg = _parse_text(args.get("tagMatch")) or TagMatch.ANY
        try:
            tag_match = TagMatch(tag_match_arg.casefold())
        except ValueError as e:
            raise InvalidFilter(f"Invalid tagMatch: {tag_match_arg!r}") from e

        language = _parse_text(args.get("language"))
        return cls(
            folders=folders("folder"),
            not_folders=folders("notFolder"),
            tags=texts("tag"),
            not_tags=texts("notTag"),
            tag_match=tag_match,
            language=language.casefold() if language is not None else None,
            author=_parse_text(args.get("author")),
            added_since=parse_date(args.get("addedSince")),
            added_before=parse_date(args.get("addedBefore")),
        )

    def to_params(self) -> Mapping[str, str | tuple[str, ...]]:
        """The query parameters that represent this filter.

        Repeated parameters are given as tuples, for use with
        ``urlencode(..., doseq=True)``.
        """
        values: Mapping[str, str | tuple[str, ...] | None] = {
            "folder": tuple(folder.as_posix() for folder in self.folders),
            "notFolder": tuple(folder.as_posix() for folder in self.not_folders),
            "tag": self.tags,
            "notTag": self.not_tags,
            "tagMatch": (
                self.tag_match.value if self.tag_match is not TagMatch.ANY else None
            ),
            "language": self.language,
            "author": self.author,
            "addedSince": (
                self.added_since.isoformat() if self.added_since is not None else None
            ),
            "addedBefore": (
                self.added_before.isoformat() if self.added_before is not None else None
            ),
        }
        return {name: value for name, value in values.items() if value}

    def without_folders(self) -> Self:
        """This filter, without the folder criteria."""
        return attrs.evolve(self, folders=(), not_folders=())

    def matches(self, entry: oh.Entry, book: oh.Book | None) -> bool:
        """Whether an entry (and the book it refers to) meets all the criteria.

        ``addedSince`` is inclusive and ``addedBefore`` is exclusive, and both
        are compared against the UTC date the entry was added.
        """
        if self.folders and not any(in_folder(entry, f) for f in self.folders):
            return False

        if any(in_folder(entry, folder) for folder in self.not_folders):
            return False

        if self.added_since is not None or self.added_before is not None:
            if entry.date_added is None:
                return False
            date_added = entry.date_added.astimezone(datetime.UTC).date()
            if self.added_since is not None and date_added < self.added_since:
                return False
            if self.added_before is not None and date_added >= self.added_before:
                return False

        book_tags = (
            {tag.casefold() for tag in book.tags or ()} if book is not None else set()
        )

        if not book_tags.isdisjoint(self.not_tags):
            return False

        if self.tags:
            if self.tag_match is TagMatch.ALL:
                if not book_tags.issuperset(self.tags):
                    return False
            elif book_tags.isdisjoint(self.tags):
                return False

        if self.language is None and self.author is None:
            return True

        if book is None:
            return False

        if self.language is not None and (book.language or "").casefold() != (
            self.language
        ):
            return False

        if self.author is not None:
            author = _normalize(self.author)
            if not any(author in _normalize(name) for name in book.authors or ()):
                return False

        return True

    def apply(
        self, entries: Iterable[oh.Entry], books: Mapping[ID, oh.Book]
    ) -> Sequence[oh.Entry]:
        return [
            entry
            for entry in entries
            if self.matches(
                entry, books.get(entry.data_id) if entry.data_id is not None else None
            )
        ]


@attrs.frozen
class Facets:
    """The values available to filter on, with the number of books for each."""

    tags: Sequence[tuple[str, int]]
    languages: Sequence[tuple[str, int]]


def facets(books: Iterable[oh.Book]) -> Facets:
    """Count the tags and languages of ``books``, most common first."""
    tags: collections.Counter[str] = collections.Counter()
    languages: collections.Counter[str] = collections.Counter()
    for book in books:
        tags.update({tag.casefold() for tag in book.tags or ()})
        if book.language:
            languages[book.language.casefold()] += 1

    def ordered(counter: collections.Counter[str]) -> Sequence[tuple[str, int]]:
        return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))

    return Facets(tags=ordered(tags), languages=ordered(languages))
