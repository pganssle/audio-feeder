"""Tests for audio_feeder.metadata_loader"""

from collections.abc import Callable, Mapping, MutableSequence
from typing import Any, Final, TypeAlias

from audio_feeder import metadata_loader as mdl
from audio_feeder import object_handler as oh
from audio_feeder import updater
from audio_feeder._db_types import ID, TableName

from . import test_updater

VOLUMES_URL: Final[str] = "https://www.googleapis.com/books/v1/volumes"

Responder: TypeAlias = Callable[[str, Mapping[str, str]], test_updater.FakeResponse]


def _volume(google_id: str = "abc123", description: str | None = "A book.") -> dict:
    volume_info: dict[str, Any] = {
        "title": "Frankenstein",
        "authors": ["Mary Shelley"],
    }
    if description is not None:
        volume_info["description"] = description
    return {"id": google_id, "volumeInfo": volume_info}


def _found(description: str | None = "A book.") -> test_updater.FakeResponse:
    return test_updater.FakeResponse(
        json_contents={"totalItems": 1, "items": [_volume(description=description)]}
    )


NOT_FOUND = test_updater.FakeResponse(json_contents={"totalItems": 0})


class FakeLoader(mdl.GoogleBooksLoader):
    """A GoogleBooksLoader whose responses come from ``responder``."""

    def __init__(self, responder: Responder) -> None:
        super().__init__(poll_delay=0)
        self.responder = responder
        self.requests: MutableSequence[tuple[str, Mapping[str, str]]] = []

    def make_request_raw(self, url: str, **kwargs: Any) -> Any:
        params = {k: v for k, v in kwargs.get("params", {}).items() if k != "key"}
        self.requests.append((url, params))
        return self.responder(url, params)


def _always(result: test_updater.FakeResponse) -> Responder:
    return lambda url, params: result


def _book(**kwargs: Any) -> oh.Book:
    kwargs.setdefault("id", ID(1))
    kwargs.setdefault("title", "Frankenstein")
    kwargs.setdefault("authors", ["Mary Shelley"])
    return oh.Book(**kwargs)


def _update(loader: mdl.BookLoader, book: oh.Book, **kwargs: Any) -> oh.Book:
    book_updater = updater.BookDatabaseUpdater(".", metadata_loaders=(loader,))
    database = {TableName("books"): {book.id: book}}
    return book_updater.update_book_metadata(database, **kwargs)["books"][book.id]


def test_successful_fetch() -> None:
    loader = FakeLoader(_always(_found("The description")))
    book = _update(loader, _book())

    assert book.metadata_sources == ["google_books"]
    assert book.descriptions == {"google_books": "The description"}
    assert book.description == "The description"
    assert book.google_id == "abc123"
    assert loader.requests == [
        (
            VOLUMES_URL,
            {"orderBy": "relevance", "q": "inauthor:Mary Shelley+intitle:Frankenstein"},
        )
    ]

    # Already fetched, so no more requests are made
    _update(loader, book)
    assert len(loader.requests) == 1


def test_successful_fetch_without_description() -> None:
    """A book Google has no description for is still marked as fetched."""
    loader = FakeLoader(_always(_found(description=None)))
    book = _update(loader, _book())

    assert book.descriptions == {"google_books": None}
    assert book.description == ""

    _update(loader, book)
    assert len(loader.requests) == 1


def test_success_after_failure_records_description() -> None:
    """A failed fetch should not prevent storing the description later.

    The updater sets ``descriptions = {}`` on books with no descriptions, after
    which a successful fetch would mark the book as done without storing the
    description.
    """
    book = _update(FakeLoader(_always(NOT_FOUND)), _book())
    assert book.metadata_sources in (None, [])

    book = _update(FakeLoader(_always(_found("The description"))), book)
    assert book.metadata_sources == ["google_books"]
    assert book.descriptions == {"google_books": "The description"}


def test_success_preserves_other_descriptions() -> None:
    loader = FakeLoader(_always(_found("Google's description")))
    book = _update(loader, _book(descriptions={"local": "My description"}))

    assert book.descriptions == {
        "local": "My description",
        "google_books": "Google's description",
    }
    assert book.description == "My description"


def test_repairs_books_fetched_without_description() -> None:
    """Books affected by the dropped-description bug are re-fetched by ID."""
    loader = FakeLoader(
        lambda url, params: test_updater.FakeResponse(
            json_contents=_volume(description="Recovered")
        )
    )
    broken_book = _book(
        metadata_sources=["google_books"], google_id="abc123", descriptions={}
    )

    book = _update(loader, broken_book)
    assert book.descriptions == {"google_books": "Recovered"}
    assert book.metadata_sources == ["google_books"]
    assert loader.requests == [(f"{VOLUMES_URL}/abc123", {})]


def test_reload_replaces_description() -> None:
    loader = FakeLoader(_always(_found("New description")))
    book = _book(
        metadata_sources=["google_books"],
        descriptions={"google_books": "Old description"},
    )

    book = _update(loader, book, reload_metadata=True)
    assert book.descriptions == {"google_books": "New description"}
    assert book.metadata_sources == ["google_books"]
