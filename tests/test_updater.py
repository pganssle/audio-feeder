"""Tests for audio_feeder.updater"""

import contextlib
import json
import pathlib
import shutil
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Final, TypeAlias
from unittest import mock

import pytest

from audio_feeder import cache_utils
from audio_feeder import database_handler as dh
from audio_feeder import metadata_loader as mdl
from audio_feeder import object_handler as oh
from audio_feeder import updater


def _lists_to_tuple(lst: list[Any]) -> tuple[Any]:
    return tuple(
        _lists_to_tuple(item) if isinstance(item, list) else item for item in lst
    )


SessionKey: TypeAlias = tuple[str, Sequence[tuple[str, str]]]
SessionJson: TypeAlias = Mapping[str, Any]


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        json_contents: SessionJson | None = None,
        headers: Mapping[str, str] | None = None,
    ):
        self.status_code = status_code
        self._json_contents = json_contents
        self.headers = headers or {}

    def json(self) -> SessionJson | None:
        return self._json_contents


def load_response_mapping(
    responses: pathlib.Path,
) -> Mapping[SessionKey, FakeResponse]:
    with open(responses) as f:
        session_responses = json.load(f)

    return {
        _lists_to_tuple(session_key): FakeResponse(
            status_code=200, json_contents=session_response
        )
        for session_key, session_response in session_responses
    }


class FakeGoogleBooksLoader(mdl.GoogleBooksLoader):
    def __init__(
        self, *args, _response_map: Mapping[SessionKey, FakeResponse], **kwargs
    ):
        kwargs["poll_delay"] = kwargs.pop("poll_delay", 0)
        self._response_map = _response_map

        super().__init__(*args, **kwargs)

    def make_request_raw(self, *args, **kwargs):
        (url,) = args

        params = kwargs["params"]
        assert not (kwargs.keys() - {"params", "timeout"})

        key = (url, tuple(params.items()))

        return self._response_map[key]


GOOGLE_BOOKS_SEARCH_URL: Final[str] = "https://www.googleapis.com/books/v1/volumes"


def google_books_search_key(query: str) -> SessionKey:
    """The key in a response mapping for a Google Books search query."""
    return (GOOGLE_BOOKS_SEARCH_URL, (("orderBy", "relevance"), ("q", query)))


def example_response_mapping() -> Mapping[SessionKey, FakeResponse]:
    return load_response_mapping(
        pathlib.Path(__file__).parent / "data/example_google_books_responses.json"
    )


class FakeBookUpdater(updater.BookDatabaseUpdater):
    def __init__(
        self,
        books_location: pathlib.Path,
        *,
        _extra_responses: Mapping[SessionKey, FakeResponse] | None = None,
        **kwargs,
    ):
        kwargs["metadata_loaders"] = kwargs.get(
            "metadata_loaders",
            (
                FakeGoogleBooksLoader(
                    _response_map={
                        **example_response_mapping(),
                        **(_extra_responses or {}),
                    }
                ),
            ),
        )
        super().__init__(books_location, **kwargs)


@contextlib.contextmanager
def patch_book_updater(
    extra_responses: Mapping[SessionKey, FakeResponse] | None = None,
) -> Iterator[None]:
    """Run updates offline, with canned Google Books responses.

    :param extra_responses:
        Responses to add to the ones in ``example_google_books_responses.json``.
    """
    old_book_updater = updater.BookDatabaseUpdater
    try:

        class _BookUpdater(FakeBookUpdater):
            def __init__(self, books_location: pathlib.Path, **kwargs) -> None:
                super().__init__(
                    books_location, _extra_responses=extra_responses, **kwargs
                )

        updater.BookDatabaseUpdater = _BookUpdater
        with mock.patch.object(
            mdl.requests, "get", return_value=FakeResponse(status_code=403)
        ):
            yield
    finally:
        updater.BookDatabaseUpdater = old_book_updater


def test_update_books(testgen_config: pathlib.Path) -> None:
    with patch_book_updater():
        updater.update(content_type="books")


FICTION_PATHS: Final[frozenset[pathlib.Path]] = frozenset(
    pathlib.Path("audiobooks/Fiction", name)
    for name in (
        "Bram Stoker - Dracula",
        "H G Wells - The Invisible Man",
        "Louisa May Alcott - [Little Women 01] - Little Women",
        "Louisa May Alcott - [Little Women 02] - Little Men",
        "Mary Shelley - Frankenstein",
    )
)
NONFICTION_PATHS: Final[frozenset[pathlib.Path]] = frozenset(
    pathlib.Path("audiobooks/Nonfiction", name)
    for name in (
        "Charles Y M Kelvin - How to Decode CMYK Images",
        "Edith Wharton - The Writing of Fiction",
        "Thomas de Quincey - Confessions of an English Opium Eater",
    )
)
ALL_PATHS: Final[frozenset[pathlib.Path]] = FICTION_PATHS | NONFICTION_PATHS


def set_content_paths(config_dir: pathlib.Path, content_paths: str) -> None:
    """Add a content_paths setting (in YAML) to the configuration file."""
    with open(config_dir / "config.yml", "a") as f:
        f.write(f"content_paths: {content_paths}\n")
    cache_utils.clear_caches()


def entry_paths() -> Sequence[pathlib.Path]:
    """The paths of the entries in the database, sorted."""
    entries = dh.load_database()["entries"]
    return sorted(entry.path for entry in entries.values())


@pytest.fixture
def media_dir(testgen_config: pathlib.Path) -> pathlib.Path:
    return testgen_config / "static/media"


@pytest.fixture(autouse=True)
def reset_update_in_progress() -> Iterator[None]:
    yield
    updater.UPDATE_IN_PROGRESS = False


def test_update_default_content_paths(testgen_config: pathlib.Path) -> None:
    with patch_book_updater():
        updater.update()

    assert entry_paths() == sorted(ALL_PATHS)


@pytest.mark.parametrize(
    "content_paths, expected",
    [
        ("{books: audiobooks/Fiction}", FICTION_PATHS),
        ("{books: [audiobooks/Nonfiction]}", NONFICTION_PATHS),
        ("{books: [audiobooks/Fiction, audiobooks/Nonfiction]}", ALL_PATHS),
        # Overlapping directories don't add the same book twice
        ("{books: [audiobooks, audiobooks/Fiction, .]}", ALL_PATHS),
    ],
)
@pytest.mark.parametrize("content_type", [None, "books"])
def test_update_configured_content_paths(
    testgen_config: pathlib.Path,
    content_paths: str,
    expected: frozenset[pathlib.Path],
    content_type: str | None,
) -> None:
    set_content_paths(testgen_config, content_paths)
    with patch_book_updater():
        updater.update(content_type=content_type)

    assert entry_paths() == sorted(expected)


def test_update_absolute_content_path(
    testgen_config: pathlib.Path, media_dir: pathlib.Path
) -> None:
    set_content_paths(testgen_config, f"{{books: '{media_dir}/audiobooks/Fiction'}}")
    with patch_book_updater():
        updater.update()

    assert entry_paths() == sorted(FICTION_PATHS)


def test_update_follows_symlinks(
    testgen_config: pathlib.Path, media_dir: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    # Content from outside the media directory can be added by linking to it
    elsewhere = tmp_path / "elsewhere"
    (media_dir / "audiobooks/Fiction").rename(elsewhere)
    (media_dir / "library").mkdir()
    (media_dir / "library/fiction").symlink_to(elsewhere, target_is_directory=True)

    set_content_paths(testgen_config, "{books: library}")
    with patch_book_updater():
        updater.update()

    assert entry_paths() == sorted(
        pathlib.Path("library/fiction", path.name) for path in FICTION_PATHS
    )


@pytest.mark.parametrize("absolute", [False, True])
@pytest.mark.parametrize("content_type", [None, "books"])
def test_update_explicit_path(
    testgen_config: pathlib.Path,
    media_dir: pathlib.Path,
    absolute: bool,
    content_type: str | None,
) -> None:
    # An explicit path is used instead of the configured paths
    set_content_paths(testgen_config, "{books: audiobooks/Fiction}")
    path = pathlib.Path("audiobooks/Nonfiction")
    if absolute:
        path = media_dir / path

    with patch_book_updater():
        updater.update(content_type=content_type, path=path)

    assert entry_paths() == sorted(NONFICTION_PATHS)


@pytest.mark.parametrize("content_paths", ["{}", "{books: []}", "{books: null}"])
@pytest.mark.parametrize("content_type", [None, "books"])
def test_update_nothing_configured(
    testgen_config: pathlib.Path, content_paths: str, content_type: str | None
) -> None:
    set_content_paths(testgen_config, content_paths)
    updater.UPDATE_IN_PROGRESS = True
    with patch_book_updater():
        updater.update(content_type=content_type)

    assert entry_paths() == []
    assert not updater.UPDATE_IN_PROGRESS


@pytest.mark.parametrize(
    "content_paths, kwargs, match",
    [
        ("{books: .}", {"content_type": "courses"}, "Unknown content type: courses"),
        (
            "{books: .}",
            {"content_type": "courses", "path": "audiobooks"},
            "Unknown content type: courses",
        ),
        (
            "{books: ., courses: c, plays: p}",
            {},
            "Unknown content types in content_paths: courses, plays",
        ),
        ("{books: ..}", {}, "not inside the media directory"),
        ("{books: [audiobooks, /]}", {}, "not inside the media directory"),
        ("{books: .}", {"path": "../media_cache"}, "not inside the media directory"),
    ],
)
def test_update_invalid(
    testgen_config: pathlib.Path,
    content_paths: str,
    kwargs: Mapping[str, Any],
    match: str,
) -> None:
    set_content_paths(testgen_config, content_paths)
    updater.UPDATE_IN_PROGRESS = True
    with patch_book_updater(), pytest.raises(ValueError, match=match):
        updater.update(**kwargs)

    assert entry_paths() == []
    assert not updater.UPDATE_IN_PROGRESS


###
# Books whose directory names don't match the expected format (#104)
UNPARSEABLE_FOUND: Final[str] = "Dracula"
UNPARSEABLE_NOT_FOUND: Final[str] = "Some Recording (2007)"
NOT_FOUND_RESPONSE: Final[FakeResponse] = FakeResponse(
    json_contents={"kind": "books#volumes", "totalItems": 0}
)
EXAMPLE_AUTHORS: Final[frozenset[str]] = frozenset(
    (
        "Bram Stoker",
        "H G Wells",
        "Louisa May Alcott",
        "Mary Shelley",
        "Charles Y M Kelvin",
        "Edith Wharton",
        "Thomas de Quincey",
    )
)


def unparseable_book_responses() -> Mapping[SessionKey, FakeResponse]:
    """Google Books responses for the books added by add_unparseable_book.

    Without an author, these are looked up by title alone.
    """
    examples = example_response_mapping()
    return {
        google_books_search_key(f"intitle:{UNPARSEABLE_FOUND}"): examples[
            google_books_search_key("inauthor:Bram Stoker+intitle:Dracula")
        ],
        google_books_search_key(f"intitle:{UNPARSEABLE_NOT_FOUND}"): (
            NOT_FOUND_RESPONSE
        ),
    }


def add_unparseable_book(media_dir: pathlib.Path, name: str) -> pathlib.Path:
    """Add a book in a directory whose name has no author.

    :return:
        The path of the new book, relative to the media directory.
    """
    rel_path = pathlib.Path("audiobooks/Fiction", name)
    shutil.copytree(
        media_dir / "audiobooks/Fiction/Bram Stoker - Dracula", media_dir / rel_path
    )
    return rel_path


def book_for_path(path: pathlib.Path) -> oh.Book:
    database = dh.load_database()
    (entry,) = (e for e in database["entries"].values() if e.path == path)
    book = database["books"][entry.data_id]
    assert isinstance(book, oh.Book)
    return book


@pytest.mark.parametrize("name", [UNPARSEABLE_FOUND, UNPARSEABLE_NOT_FOUND])
def test_update_unparseable_directory_name(
    testgen_config: pathlib.Path,
    media_dir: pathlib.Path,
    name: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = add_unparseable_book(media_dir, name)
    with patch_book_updater(unparseable_book_responses()):
        updater.update(content_type="books")

    # The update finishes, and every book is saved
    assert entry_paths() == sorted(ALL_PATHS | {path})

    # The book is listed under its directory name, with no author
    book = book_for_path(path)
    assert book.title == name
    assert not book.authors
    assert not book.author_ids

    # ... and the user is told why
    assert any(
        record.levelname == "WARNING" and name in record.getMessage()
        for record in caplog.records
    )

    # The other books still have their authors
    dracula = book_for_path(pathlib.Path("audiobooks/Fiction/Bram Stoker - Dracula"))
    assert dracula.authors == ["Bram Stoker"]


def test_update_unparseable_directory_metadata(
    testgen_config: pathlib.Path, media_dir: pathlib.Path
) -> None:
    found = add_unparseable_book(media_dir, UNPARSEABLE_FOUND)
    not_found = add_unparseable_book(media_dir, UNPARSEABLE_NOT_FOUND)
    with patch_book_updater(unparseable_book_responses()):
        updater.update(content_type="books")

    # Metadata is still looked up by title, but the author isn't filled in
    # from a search that may well have matched some other book.
    found_book = book_for_path(found)
    assert found_book.google_id is not None
    assert not found_book.authors

    not_found_book = book_for_path(not_found)
    assert not_found_book.google_id is None
    assert not not_found_book.authors

    # Neither one adds an author
    authors = dh.load_database()["authors"]
    assert {author.name for author in authors.values()} == EXAMPLE_AUTHORS


def test_update_unparseable_directory_twice(
    testgen_config: pathlib.Path, media_dir: pathlib.Path
) -> None:
    path = add_unparseable_book(media_dir, UNPARSEABLE_FOUND)
    with patch_book_updater(unparseable_book_responses()):
        updater.update(content_type="books")
        book_id = book_for_path(path).id

        # Updating again keeps the same book, rather than adding another one
        updater.update(content_type="books")

    assert book_for_path(path).id == book_id
    assert entry_paths() == sorted(ALL_PATHS | {path})
    assert len(dh.load_database()["books"]) == len(ALL_PATHS) + 1
