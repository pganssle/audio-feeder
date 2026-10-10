"""Tests for audio_feeder.entry_filters"""

import datetime
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

import pytest
from hypothesis import given
from hypothesis import strategies as st

from audio_feeder import entry_filters as ef
from audio_feeder import object_handler as oh
from audio_feeder._db_types import ID

# A library with a single top-level folder, with books at different depths
PATHS = (
    "audiobooks/Fiction/Science Fiction/Ada Example - Starfall",
    "audiobooks/Fiction/Science Fiction/Ben Sample - Orbits",
    "audiobooks/Fiction/Fantasy/Cleo Placeholder - The Ninth Gate",
    "audiobooks/Nonfiction/History/Dev Testcase - A History of Bridges",
    "audiobooks/Nonfiction/History/Ancient/Eva Fixture - Old Empires",
    "audiobooks/Poetry/Finn Mock - Collected Verse",
)


def _entries(paths: Sequence[str]) -> Sequence[oh.Entry]:
    return [oh.Entry(id=ID(i), path=Path(path)) for i, path in enumerate(paths)]


def _folder(folder: str | None) -> PurePosixPath | None:
    return PurePosixPath(folder) if folder is not None else None


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        ("", None),
        ("/", None),
        (".", None),
        ("audiobooks", PurePosixPath("audiobooks")),
        ("audiobooks/Fiction", PurePosixPath("audiobooks/Fiction")),
        ("/audiobooks//Fiction/", PurePosixPath("audiobooks/Fiction")),
        ("audiobooks/./Fiction", PurePosixPath("audiobooks/Fiction")),
        ("Science & Nature", PurePosixPath("Science & Nature")),
    ],
)
def test_parse_folder(value: str | None, expected: PurePosixPath | None) -> None:
    assert ef.parse_folder(value) == expected


@pytest.mark.parametrize("value", ["..", "../secrets", "audiobooks/../.."])
def test_parse_folder_rejects_parent_references(value: str) -> None:
    with pytest.raises(ef.InvalidFilter):
        ef.parse_folder(value)


@pytest.mark.parametrize(
    "folder, expected_count",
    [
        (None, 6),
        ("audiobooks", 6),
        ("audiobooks/Fiction", 3),
        ("audiobooks/Fiction/Science Fiction", 2),
        ("audiobooks/Nonfiction/History", 2),
        ("audiobooks/Nonfiction/History/Ancient", 1),
        # Prefix of a folder name is not the folder
        ("audiobooks/Fic", 0),
        # A book's own directory is not a folder containing it
        ("audiobooks/Poetry/Finn Mock - Collected Verse", 0),
        ("Nonexistent", 0),
    ],
)
def test_filter_by_folder(folder: str | None, expected_count: int) -> None:
    entry_filter = ef.EntryFilter(folder=_folder(folder))
    assert len(entry_filter.apply(_entries(PATHS), {})) == expected_count


@pytest.mark.parametrize(
    "folder, expected",
    [
        # Every entry is below `audiobooks/`, so that level is skipped
        (None, {"Fiction": 3, "Nonfiction": 2, "Poetry": 1}),
        ("audiobooks", {"Fiction": 3, "Nonfiction": 2, "Poetry": 1}),
        ("audiobooks/Fiction", {"Fantasy": 1, "Science Fiction": 2}),
        # Nonfiction only contains History, so that level is skipped too
        ("audiobooks/Nonfiction", {"Ancient": 1}),
        ("audiobooks/Nonfiction/History", {"Ancient": 1}),
        # Folders that contain only books have no subfolders
        ("audiobooks/Poetry", {}),
        ("audiobooks/Fiction/Fantasy", {}),
        ("Nonexistent", {}),
    ],
)
def test_subfolders(folder: str | None, expected: dict[str, int]) -> None:
    result = ef.subfolders(_entries(PATHS), _folder(folder))
    assert {sub.name: sub.count for sub in result} == expected
    assert [sub.folder for sub in result] == sorted(sub.folder for sub in result)


_names = st.sampled_from(["a", "b", "c", "Science Fiction"])
_paths = st.lists(_names, min_size=1, max_size=4).map(lambda parts: "/".join(parts))


@given(paths=st.lists(_paths, max_size=20), folder=st.none() | _paths)
def test_subfolder_counts_match_filter(paths: list[str], folder: str | None) -> None:
    entries = _entries(paths)
    parent = _folder(folder)
    for sub in ef.subfolders(entries, parent):
        assert parent is None or parent in sub.folder.parents
        assert sub.count == len(ef.EntryFilter(folder=sub.folder).apply(entries, {}))
        assert sub.count > 0


@pytest.mark.parametrize(
    "folder, expected",
    [
        (None, []),
        ("audiobooks", ["audiobooks"]),
        (
            "audiobooks/Fiction/Fantasy",
            ["audiobooks", "audiobooks/Fiction", "audiobooks/Fiction/Fantasy"],
        ),
    ],
)
def test_breadcrumbs(folder: str | None, expected: list[str]) -> None:
    assert ef.breadcrumbs(_folder(folder)) == [PurePosixPath(p) for p in expected]


@pytest.mark.parametrize(
    "args, expected_params",
    [
        ({}, {}),
        ({"folder": ""}, {}),
        ({"folder": "/audiobooks/Fiction/"}, {"folder": "audiobooks/Fiction"}),
        ({"folder": "audiobooks", "page": "2"}, {"folder": "audiobooks"}),
    ],
)
def test_filter_params_round_trip(
    args: dict[str, str], expected_params: dict[str, str]
) -> None:
    entry_filter = ef.EntryFilter.from_args(args)
    assert entry_filter.to_params() == expected_params
    assert ef.EntryFilter.from_args(entry_filter.to_params()) == entry_filter


_UTC = datetime.UTC


def _book(**kwargs: object) -> oh.Book:
    kwargs.setdefault("id", ID(100))
    return oh.Book(**kwargs)  # type: ignore[arg-type]


def _entry(
    date_added: datetime.datetime | None = None, data_id: int | None = 100
) -> oh.Entry:
    return oh.Entry(
        id=ID(1),
        path=Path("audiobooks/Fiction/Author - Title"),
        date_added=date_added,
        data_id=ID(data_id) if data_id is not None else None,
    )


@pytest.mark.parametrize(
    "args, expected",
    [
        ({"tag": " Fiction "}, ef.EntryFilter(tag="fiction")),
        ({"language": "EN"}, ef.EntryFilter(language="en")),
        ({"author": "  Mary Shelley "}, ef.EntryFilter(author="Mary Shelley")),
        (
            {"addedSince": "2024-01-31", "addedBefore": "2025-02-01"},
            ef.EntryFilter(
                added_since=datetime.date(2024, 1, 31),
                added_before=datetime.date(2025, 2, 1),
            ),
        ),
        # Empty fields, as submitted by the form, mean no filter
        (
            {"tag": "", "language": "", "author": " ", "addedSince": "", "folder": ""},
            ef.EntryFilter(),
        ),
    ],
)
def test_filter_from_args(args: Mapping[str, str], expected: ef.EntryFilter) -> None:
    entry_filter = ef.EntryFilter.from_args(args)
    assert entry_filter == expected
    assert ef.EntryFilter.from_args(entry_filter.to_params()) == entry_filter


@pytest.mark.parametrize(
    "args", [{"addedSince": "yesterday"}, {"addedBefore": "2024-13-01"}]
)
def test_filter_from_args_invalid_date(args: Mapping[str, str]) -> None:
    with pytest.raises(ef.InvalidFilter):
        ef.EntryFilter.from_args(args)


@pytest.mark.parametrize(
    "entry_filter, book, expected",
    [
        (ef.EntryFilter(tag="fiction"), _book(tags=["Fiction", "Horror"]), True),
        (ef.EntryFilter(tag="fiction"), _book(tags=["history"]), False),
        (ef.EntryFilter(tag="fiction"), _book(tags=None), False),
        (ef.EntryFilter(language="en"), _book(language="EN"), True),
        (ef.EntryFilter(language="en"), _book(language="es"), False),
        (ef.EntryFilter(language="en"), _book(language=None), False),
        (ef.EntryFilter(author="shelley"), _book(authors=["Mary Shelley"]), True),
        (ef.EntryFilter(author="Wells"), _book(authors=["H G Wells", "X"]), True),
        # Accents and case are ignored, in both directions
        (ef.EntryFilter(author="zoe"), _book(authors=["Zoë Exämple"]), True),
        (ef.EntryFilter(author="ZOË"), _book(authors=["Zoe Example"]), True),
        (ef.EntryFilter(author="shelley"), _book(authors=["H G Wells"]), False),
        (ef.EntryFilter(author="shelley"), _book(authors=None), False),
        (
            ef.EntryFilter(tag="fiction", author="shelley"),
            _book(tags=["fiction"], authors=["H G Wells"]),
            False,
        ),
        (ef.EntryFilter(), None, True),
        (ef.EntryFilter(tag="fiction"), None, False),
    ],
)
def test_filter_matches_book_metadata(
    entry_filter: ef.EntryFilter, book: oh.Book | None, expected: bool
) -> None:
    assert entry_filter.matches(_entry(), book) is expected


@pytest.mark.parametrize(
    "date_added, expected",
    [
        (None, False),
        (datetime.datetime(2024, 12, 31, 23, 59, tzinfo=_UTC), False),
        # addedSince is inclusive
        (datetime.datetime(2025, 1, 1, 0, 0, tzinfo=_UTC), True),
        (datetime.datetime(2025, 1, 31, 23, 59, tzinfo=_UTC), True),
        # addedBefore is exclusive
        (datetime.datetime(2025, 2, 1, 0, 0, tzinfo=_UTC), False),
        # Dates are compared in UTC: this is 2025-02-01 in UTC
        (
            datetime.datetime(
                2025,
                1,
                31,
                20,
                0,
                tzinfo=datetime.timezone(-datetime.timedelta(hours=5)),
            ),
            False,
        ),
    ],
)
def test_filter_matches_date_added(
    date_added: datetime.datetime | None, expected: bool
) -> None:
    entry_filter = ef.EntryFilter(
        added_since=datetime.date(2025, 1, 1), added_before=datetime.date(2025, 2, 1)
    )
    assert entry_filter.matches(_entry(date_added=date_added), _book()) is expected


def test_filter_apply_looks_up_books() -> None:
    entries = [_entry(data_id=100), _entry(data_id=101), _entry(data_id=None)]
    books = {
        ID(100): _book(id=ID(100), tags=["fiction"]),
        ID(101): _book(id=ID(101), tags=["history"]),
    }
    result = ef.EntryFilter(tag="fiction").apply(entries, books)
    assert [entry.data_id for entry in result] == [ID(100)]


def test_facets() -> None:
    books = [
        _book(tags=["Fiction", "Horror"], language="en"),
        _book(tags=["fiction"], language="EN"),
        _book(tags=["history", "History"], language="es"),
        _book(tags=None, language=None),
    ]
    result = ef.facets(books)
    # Most common first, then alphabetical; tags are counted once per book
    assert result.tags == [("fiction", 2), ("history", 1), ("horror", 1)]
    assert result.languages == [("en", 2), ("es", 1)]
