"""
Book handlers
"""

import datetime
import types
import typing
from concurrent import futures
from pathlib import Path
from typing import Mapping, MutableMapping, Optional, Sequence, Tuple, Union

import attrs

from . import hash_utils
from ._compat import Self
from ._db_types import ID, TableName
from ._object_types import SchemaType, TypeName
from .file_probe import FileInfo


def _filter_sparse(_: attrs.Attribute, value: typing.Any) -> bool:
    return value is not None


_ST = typing.TypeVar("_ST", bound=SchemaType)
_TYPE_MAPPING: typing.MutableMapping[TypeName, SchemaType] = {}
_TABLE_MAPPING: typing.MutableMapping[TableName, TypeName] = {}

TYPE_MAPPING: typing.Mapping[TypeName, SchemaType] = types.MappingProxyType(
    _TYPE_MAPPING
)
TABLE_MAPPING: typing.Mapping[TableName, TypeName] = types.MappingProxyType(
    _TABLE_MAPPING
)


def _register_type(table_name: str) -> typing.Callable[[_ST], _ST]:
    table_name_: TableName = TableName(table_name)

    def register_type(t: _ST) -> _ST:
        type_name = TypeName(t.__name__)
        _TYPE_MAPPING[type_name] = t
        _TABLE_MAPPING[table_name_] = type_name
        return t

    return register_type


class BaseObject:
    id: ID

    def to_dict(self) -> typing.Mapping[str, typing.Any]:
        return attrs.asdict(self)

    def to_dict_sparse(
        self, *, _filter=_filter_sparse
    ) -> typing.Mapping[str, typing.Any]:
        return attrs.asdict(self, filter=_filter)

    def copy(self: Self) -> Self:
        """Make a new copy of this object."""
        return attrs.evolve(self)


# SqlAlchemy has problems with slots ☹
@_register_type("entries")
@attrs.define(slots=False, repr=True)
class Entry(BaseObject):
    id: ID = attrs.field(metadata={"required": True, "primary_key": True})
    path: Path = attrs.field(metadata={"required": True})
    cover_images: Optional[Sequence[Path]] = None
    date_added: Optional[datetime.datetime] = None
    last_modified: Optional[datetime.datetime] = None

    type: Optional[str] = None
    table: Optional[str] = None
    data_id: ID = attrs.field(default=None, metadata={"required": True})
    hashseed: Optional[int] = None
    files: Optional[Sequence[Path]] = None
    file_metadata: Optional[Mapping[Path, FileInfo]] = None
    file_hashes: Optional[Mapping[Path, str]] = None

    def updated_hashes(self, base_path: Path) -> Tuple[Mapping[Path, str], bool]:
        if self.files is None:
            raise ValueError("entry.files must not be None when calculating hashes")

        if self.hashseed is None:
            raise ValueError("Entry must have a hash seed to calculate hashes.")

        hashseed = self.hashseed

        new_hashes: MutableMapping[Path, str] = {}
        hash_mismatch = self.file_hashes is None
        file_hashes = self.file_hashes or {}

        for file in self.files:
            abs_path = base_path / file
            if not abs_path.exists():
                raise FileNotFoundError(
                    "Some files included in the entry were not found!"
                )
            new_hashes[file] = hash_utils.hash_random(abs_path, hashseed).hex()
            if not hash_mismatch and new_hashes[file] != file_hashes[file]:
                hash_mismatch = True

        if hash_mismatch:
            return (new_hashes, True)
        else:
            return (file_hashes, False)

    def updated_metadata(
        self, base_path: Path, *, executor: Optional[futures.Executor] = None
    ) -> Self:
        if executor is None:
            executor = futures.ThreadPoolExecutor()

        new_hashes, hash_changed = self.updated_hashes(base_path)
        assert self.files is not None

        if hash_changed:
            file_metadata = {}
            file_metadata_futures = iter(
                executor.map(
                    lambda file: (file, FileInfo.from_file(base_path / file)),
                    self.files,
                )
            )
            while True:
                try:
                    file, file_info = next(file_metadata_futures)
                except StopIteration:
                    break
                # TODO: Update the file_probe metadata probes to raise errors
                # from a module-specific hierarchy, and catch those.
                except Exception:
                    continue
                else:
                    file_metadata[file] = file_info

            self.file_hashes = new_hashes
            self.file_metadata = file_metadata

        return self


@_register_type("books")
@attrs.define(slots=False, repr=True)
class Book(BaseObject):
    """Represents a book."""

    id: ID = attrs.field(metadata={"required": True, "primary_key": True})

    # Book information
    isbn: Optional[str] = None
    isbn13: Optional[str] = None
    oclc: Optional[str] = None
    lccn: Optional[str] = None
    issn: Optional[str] = None
    google_id: Optional[str] = None
    goodreads_id: Optional[str] = None
    ASIN: Optional[str] = None
    metadata_sources: Optional[Sequence[str]] = None

    pub_date: Optional[str] = None
    original_pub_date: Optional[str] = None
    publisher: Optional[str] = None

    tags: Optional[Sequence[str]] = None
    duration: Optional[float] = None
    pages: Optional[int] = None

    title: Optional[str] = None
    subtitle: Optional[str] = None

    authors: Optional[Sequence[str]] = None
    author_ids: Optional[Sequence[ID]] = attrs.field(
        default=None,
        metadata={
            "foreign_key": "authors.id",
            "comment": "Foreign key to the authors table.",
        },
    )
    author_roles: Optional[Sequence[int]] = attrs.field(
        default=None,
        metadata={"comment": "Author = 0, Narrator = 1, Contributor = 2, Editor = 3"},
    )
    description: Optional[str] = None
    descriptions: Optional[Mapping[str, str]] = attrs.field(
        default=None, metadata={"comment": "Cache multiple descriptions by source"}
    )

    # Series information will be three corresponding lists, with the
    # primary series as the first entry in the list.
    series_id: Optional[Sequence[int]] = attrs.field(
        default=None,
        metadata={
            "foreign_key": "series.id",
            "comment": "Foreign key to the series table.",
        },
    )
    series_name: Optional[Sequence[str]] = None
    series_number: Optional[Sequence[int]] = None

    cover_images: Optional[Mapping[str, Union[Path, Mapping[str, str]]]] = None

    language: Optional[str] = None


@_register_type("authors")
@attrs.define(slots=False, repr=True)
class Author(BaseObject):
    """Represents a book author."""

    id: ID = attrs.field(metadata={"required": True, "primary_key": True})

    # Author information
    name: Optional[str] = None
    sort_name: Optional[str] = None
    books: Optional[Sequence[int]] = attrs.field(
        default=None,
        metadata={
            "foreign_key": "books.id",
            "comment": "Foreign key to the books table.",
        },
    )
    tags: Optional[Sequence[str]] = None

    # Miscellaneous information
    description: Optional[str] = attrs.field(
        default=None, metadata={"comment": "Biographical information"}
    )
    images: Optional[Sequence[Path]] = None
    alternate_names: Optional[Sequence[str]] = None
    website: Optional[str] = None
    birthdate: Optional[datetime.date] = None
    deathdate: Optional[datetime.date] = None


@_register_type("series")
@attrs.define(slots=False, repr=True)
class Series(BaseObject):
    """Represents a related series of books or other data items."""

    id: ID = attrs.field(metadata={"required": True, "primary_key": True})

    # Series information
    name: Optional[str] = attrs.field(
        default=None,
        metadata={"comment": "Series names will be of the form 'name (modifier)'"},
    )
    modifier: Optional[str] = attrs.field(
        default=None,
        metadata={
            "comment": "The modifier is used for disambiguating alternate "
            "versions of a series with different subsets or orders."
        },
    )
    name_with_modifier: Optional[str] = None

    data_ids: Optional[Sequence[int]] = attrs.field(
        default=None,
        metadata={
            "comment": "List of keys to components - these are foreign keys to "
            "potentially multiple tables."
        },
    )
    data_numbers: Optional[Sequence[float]] = attrs.field(
        default=None,
        metadata={
            "comment": "A list, the same size as data_ids, of the "
            "corresponding series numbering."
        },
    )
    data_tables: Optional[Sequence[str]] = attrs.field(
        default=None, metadata={"comment": "The tables to find the data ids in."}
    )
    authors: Optional[Sequence[str]] = attrs.field(
        default=None,
        metadata={
            "foreign_key": "authors.id",
            "comment": "Foreign key into the authors table.",
        },
    )

    alternate_orders: Optional[Sequence[int]] = attrs.field(
        default=None,
        metadata={
            "comment": "IDs of other series representing the same books in a "
            "different order."
        },
    )

    superseries: Optional[Sequence[int]] = attrs.field(
        default=None,
        metadata={
            "comment": "When a series is a subset of a larger series, "
            "e.g. 'Ender's Shadow' as a subset of 'Ender's Game' or "
            "'Ringworld' as a subset of 'Known Space'. These are the ids of "
            "the superseries to whcih this series belongs."
        },
    )

    related_series: Optional[Sequence[int]] = None
