"""Tests for audio_feeder.updater"""

import contextlib
import json
import pathlib
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Final, TypeAlias
from unittest import mock

import pytest

from audio_feeder import cache_utils
from audio_feeder import database_handler as dh
from audio_feeder import metadata_loader as mdl
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


class FakeBookUpdater(updater.BookDatabaseUpdater):
    def __init__(self, books_location: pathlib.Path, **kwargs):
        kwargs["metadata_loaders"] = kwargs.get(
            "metadata_loaders",
            (
                FakeGoogleBooksLoader(
                    _response_map=load_response_mapping(
                        pathlib.Path(__file__).parent
                        / "data/example_google_books_responses.json"
                    )
                ),
            ),
        )
        super().__init__(books_location, **kwargs)


@contextlib.contextmanager
def patch_book_updater() -> Iterator[None]:
    old_book_updater = updater.BookDatabaseUpdater
    try:
        updater.BookDatabaseUpdater = FakeBookUpdater
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
