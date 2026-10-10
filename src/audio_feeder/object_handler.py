"""
Book handlers
"""

import datetime
import enum
import types
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from concurrent import futures
from pathlib import Path
from typing import Any, Self, TypeVar

import attrs

from . import hash_utils
from ._db_types import ID, TableName
from ._object_types import SchemaType, TypeName
from .file_probe import FileInfo


def _filter_sparse(_: attrs.Attribute, value: Any) -> bool:
    return value is not None


_ST = TypeVar("_ST", bound=SchemaType)
_TYPE_MAPPING: MutableMapping[TypeName, SchemaType] = {}
_TABLE_MAPPING: MutableMapping[TableName, TypeName] = {}

TYPE_MAPPING: Mapping[TypeName, SchemaType] = types.MappingProxyType(_TYPE_MAPPING)
TABLE_MAPPING: Mapping[TableName, TypeName] = types.MappingProxyType(_TABLE_MAPPING)


def _register_type(table_name: str) -> Callable[[_ST], _ST]:
    table_name_: TableName = TableName(table_name)

    def register_type(t: _ST) -> _ST:
        type_name = TypeName(t.__name__)
        _TYPE_MAPPING[type_name] = t
        _TABLE_MAPPING[table_name_] = type_name
        return t

    return register_type


class BaseObject:
    id: ID

    def to_dict(self) -> Mapping[str, Any]:
        return attrs.asdict(self)  # type: ignore[arg-type]

    def to_dict_sparse(self, *, _filter=_filter_sparse) -> Mapping[str, Any]:
        # Nested attrs classes (e.g. FileInfo) are left for the serializer.
        return attrs.asdict(self, filter=_filter, recurse=False)  # type: ignore[arg-type]

    def copy(self: Self) -> Self:
        """Make a new copy of this object."""
        return attrs.evolve(self)  # type: ignore[misc]


# SqlAlchemy has problems with slots ☹
@_register_type("entries")
@attrs.define(slots=False, repr=True)
class Entry(BaseObject):
    id: ID = attrs.field(metadata={"required": True, "primary_key": True})
    path: Path = attrs.field(metadata={"required": True})
    cover_images: Sequence[Path] | None = None
    date_added: datetime.datetime | None = None
    last_modified: datetime.datetime | None = None

    type: str | None = None
    table: str | None = None
    data_id: ID | None = attrs.field(default=None, metadata={"required": True})
    hashseed: int | None = None
    files: Sequence[Path] | None = None
    file_metadata: Mapping[Path, FileInfo] | None = None
    file_hashes: Mapping[Path, str] | None = None

    def updated_hashes(self, base_path: Path) -> tuple[Mapping[Path, str], bool]:
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
        self, base_path: Path, *, executor: futures.Executor | None = None
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


class FetchOutcome(enum.StrEnum):
    """Why the most recent attempt to fetch metadata from a source failed."""

    NOT_FOUND = "not_found"
    """The source answered, but had no matching record."""

    REJECTED = "rejected"
    """The source refused this specific query (e.g. a 400 Bad Request)."""

    UNAVAILABLE = "unavailable"
    """The source could not be queried (quota, network or server errors)."""


@attrs.frozen
class MetadataFetchStatus:
    """Records a failed attempt to fetch metadata for a book from one source.

    Successful fetches are recorded in ``Book.metadata_sources`` instead, and
    clear any existing failure status for that source.
    """

    outcome: FetchOutcome = attrs.field(converter=FetchOutcome)
    last_attempt: datetime.datetime
    query_key: str = attrs.field(
        metadata={
            "comment": "Fingerprint of the information used to query the source. "
            "If it changes (e.g. the title is corrected), the failure no longer "
            "applies."
        }
    )
    failures: int = attrs.field(
        default=0,
        metadata={
            "comment": "Number of consecutive NOT_FOUND or REJECTED responses "
            "for this query_key; this determines how long to wait before retrying."
        },
    )
    retry_after: datetime.datetime | None = None
    message: str | None = None

    def to_json(self) -> Mapping[str, Any]:
        out: dict[str, Any] = {
            "outcome": self.outcome.value,
            "last_attempt": self.last_attempt.isoformat(),
            "query_key": self.query_key,
            "failures": self.failures,
        }
        if self.retry_after is not None:
            out["retry_after"] = self.retry_after.isoformat()
        if self.message is not None:
            out["message"] = self.message
        return out

    @classmethod
    def from_json(cls, json_obj: Mapping[str, Any]) -> Self:
        retry_after = json_obj.get("retry_after", None)
        return cls(
            outcome=json_obj["outcome"],
            last_attempt=datetime.datetime.fromisoformat(json_obj["last_attempt"]),
            query_key=json_obj["query_key"],
            failures=json_obj.get("failures", 0),
            retry_after=(
                datetime.datetime.fromisoformat(retry_after)
                if retry_after is not None
                else None
            ),
            message=json_obj.get("message", None),
        )


@_register_type("books")
@attrs.define(slots=False, repr=True)
class Book(BaseObject):
    """Represents a book."""

    id: ID = attrs.field(metadata={"required": True, "primary_key": True})

    # Book information
    isbn: str | None = None
    isbn13: str | None = None
    oclc: str | None = None
    lccn: str | None = None
    issn: str | None = None
    google_id: str | None = None
    goodreads_id: str | None = None
    ASIN: str | None = None
    metadata_sources: Sequence[str] | None = None
    metadata_fetch_status: Mapping[str, MetadataFetchStatus] | None = attrs.field(
        default=None,
        metadata={"comment": "Failed metadata fetch attempts, by source"},
    )

    pub_date: str | None = None
    original_pub_date: str | None = None
    publisher: str | None = None

    tags: Sequence[str] | None = None
    duration: float | None = None
    pages: int | None = None

    title: str | None = None
    subtitle: str | None = None

    authors: Sequence[str] | None = None
    author_ids: Sequence[ID] | None = attrs.field(
        default=None,
        metadata={
            "foreign_key": "authors.id",
            "comment": "Foreign key to the authors table.",
        },
    )
    author_roles: Sequence[int] | None = attrs.field(
        default=None,
        metadata={"comment": "Author = 0, Narrator = 1, Contributor = 2, Editor = 3"},
    )
    description: str | None = None
    descriptions: Mapping[str, str] | None = attrs.field(
        default=None, metadata={"comment": "Cache multiple descriptions by source"}
    )

    # Series information will be three corresponding lists, with the
    # primary series as the first entry in the list.
    series_id: Sequence[int] | None = attrs.field(
        default=None,
        metadata={
            "foreign_key": "series.id",
            "comment": "Foreign key to the series table.",
        },
    )
    series_name: Sequence[str] | None = None
    series_number: Sequence[int] | None = None

    cover_images: Mapping[str, Path | Mapping[str, str]] | None = None

    language: str | None = None


@_register_type("authors")
@attrs.define(slots=False, repr=True)
class Author(BaseObject):
    """Represents a book author."""

    id: ID = attrs.field(metadata={"required": True, "primary_key": True})

    # Author information
    name: str | None = None
    sort_name: str | None = None
    books: Sequence[int] | None = attrs.field(
        default=None,
        metadata={
            "foreign_key": "books.id",
            "comment": "Foreign key to the books table.",
        },
    )
    tags: Sequence[str] | None = None

    # Miscellaneous information
    description: str | None = attrs.field(
        default=None, metadata={"comment": "Biographical information"}
    )
    images: Sequence[Path] | None = None
    alternate_names: Sequence[str] | None = None
    website: str | None = None
    birthdate: datetime.date | None = None
    deathdate: datetime.date | None = None


@_register_type("series")
@attrs.define(slots=False, repr=True)
class Series(BaseObject):
    """Represents a related series of books or other data items."""

    id: ID = attrs.field(metadata={"required": True, "primary_key": True})

    # Series information
    name: str | None = attrs.field(
        default=None,
        metadata={"comment": "Series names will be of the form 'name (modifier)'"},
    )
    modifier: str | None = attrs.field(
        default=None,
        metadata={
            "comment": "The modifier is used for disambiguating alternate "
            "versions of a series with different subsets or orders."
        },
    )
    name_with_modifier: str | None = None

    data_ids: Sequence[int] | None = attrs.field(
        default=None,
        metadata={
            "comment": "List of keys to components - these are foreign keys to "
            "potentially multiple tables."
        },
    )
    data_numbers: Sequence[float] | None = attrs.field(
        default=None,
        metadata={
            "comment": "A list, the same size as data_ids, of the "
            "corresponding series numbering."
        },
    )
    data_tables: Sequence[str] | None = attrs.field(
        default=None, metadata={"comment": "The tables to find the data ids in."}
    )
    authors: Sequence[str] | None = attrs.field(
        default=None,
        metadata={
            "foreign_key": "authors.id",
            "comment": "Foreign key into the authors table.",
        },
    )

    alternate_orders: Sequence[int] | None = attrs.field(
        default=None,
        metadata={
            "comment": "IDs of other series representing the same books in a "
            "different order."
        },
    )

    superseries: Sequence[int] | None = attrs.field(
        default=None,
        metadata={
            "comment": "When a series is a subset of a larger series, "
            "e.g. 'Ender's Shadow' as a subset of 'Ender's Game' or "
            "'Ringworld' as a subset of 'Known Space'. These are the ids of "
            "the superseries to whcih this series belongs."
        },
    )

    related_series: Sequence[int] | None = None
