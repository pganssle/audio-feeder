"""Tests for audio_feeder.metadata_loader"""

import datetime
from collections.abc import Callable, Mapping, MutableSequence, Sequence
from typing import Any, Final, TypeAlias

import attrs
import pytest
import requests

from audio_feeder import metadata_loader as mdl
from audio_feeder import object_handler as oh
from audio_feeder import updater
from audio_feeder._db_types import ID, TableName

from . import test_updater

NOW: Final[datetime.datetime] = datetime.datetime(2026, 10, 10, 12, tzinfo=datetime.UTC)
DAY: Final[datetime.timedelta] = datetime.timedelta(days=1)
_SECOND: Final[datetime.timedelta] = datetime.timedelta(seconds=1)
VOLUMES_URL: Final[str] = "https://www.googleapis.com/books/v1/volumes"

FakeResult: TypeAlias = test_updater.FakeResponse | Exception
Responder: TypeAlias = Callable[[str, Mapping[str, str]], FakeResult]


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

# Real response from the Google Books API, captured 2026-10-10
DAILY_QUOTA_EXCEEDED = test_updater.FakeResponse(
    status_code=429,
    json_contents={
        "error": {
            "code": 429,
            "message": "Quota exceeded for quota metric 'Queries' and limit "
            "'Queries per day' of service 'books.googleapis.com' for consumer "
            "'project_number:624717413613'.",
            "errors": [
                {
                    "message": "Quota exceeded for quota metric 'Queries' and limit "
                    "'Queries per day' of service 'books.googleapis.com' for "
                    "consumer 'project_number:624717413613'.",
                    "domain": "global",
                    "reason": "rateLimitExceeded",
                }
            ],
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "RATE_LIMIT_EXCEEDED",
                    "domain": "googleapis.com",
                    "metadata": {
                        "quota_location": "global",
                        "consumer": "projects/624717413613",
                        "quota_metric": "books.googleapis.com/default",
                        "quota_limit_value": "0",
                        "quota_limit": "defaultPerDayPerProject",
                        "quota_unit": "1/d/{project}",
                        "service": "books.googleapis.com",
                    },
                },
            ],
        }
    },
)

LEGACY_DAILY_LIMIT = test_updater.FakeResponse(
    status_code=403,
    json_contents={
        "error": {
            "code": 403,
            "message": "Daily Limit Exceeded",
            "errors": [{"reason": "dailyLimitExceeded", "domain": "usageLimits"}],
        }
    },
)

PER_MINUTE_RATE_LIMIT = test_updater.FakeResponse(
    status_code=429,
    json_contents={
        "error": {
            "code": 429,
            "message": "Quota exceeded for quota metric 'Queries' and limit "
            "'Queries per minute per user'",
            "errors": [{"reason": "rateLimitExceeded"}],
            "status": "RESOURCE_EXHAUSTED",
        }
    },
)

SERVER_ERROR = test_updater.FakeResponse(status_code=503, json_contents=None)

BAD_REQUEST = test_updater.FakeResponse(
    status_code=400,
    json_contents={"error": {"code": 400, "message": "Invalid query"}},
)

VOLUME_GONE = test_updater.FakeResponse(
    status_code=404,
    json_contents={
        "error": {"code": 404, "message": "The volume ID could not be found."}
    },
)


class FakeLoader(mdl.GoogleBooksLoader):
    """A GoogleBooksLoader whose responses come from ``responder``."""

    def __init__(self, responder: Responder) -> None:
        super().__init__(poll_delay=0)
        self.responder = responder
        self.requests: MutableSequence[tuple[str, Mapping[str, str]]] = []

    def make_request_raw(self, url: str, **kwargs: Any) -> Any:
        params = {k: v for k, v in kwargs["params"].items() if k != "key"}
        self.requests.append((url, params))
        result = self.responder(url, params)
        if isinstance(result, Exception):
            raise result
        return result


def _always(result: FakeResult) -> Responder:
    return lambda url, params: result


def _sequence(*results: FakeResult) -> Responder:
    results_iter = iter(results)
    return lambda url, params: next(results_iter)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> Sequence[float]:
    """Record calls to time.sleep rather than actually sleeping."""
    slept: list[float] = []
    monkeypatch.setattr(mdl.time, "sleep", slept.append)
    return slept


def _book(**kwargs: Any) -> oh.Book:
    kwargs.setdefault("id", ID(1))
    kwargs.setdefault("title", "Frankenstein")
    kwargs.setdefault("authors", ["Mary Shelley"])
    return oh.Book(**kwargs)


def _status(book: oh.Book) -> oh.MetadataFetchStatus:
    assert book.metadata_fetch_status is not None
    return book.metadata_fetch_status["google_books"]


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
    book = _update(FakeLoader(_always(DAILY_QUOTA_EXCEEDED)), _book())
    assert book.metadata_sources is None

    # A new loader, as on the next update after the quota resets
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


def test_already_fetched_makes_no_requests() -> None:
    loader = FakeLoader(_always(AssertionError("Should not be called")))
    book = _book(metadata_sources=["google_books"], descriptions={"google_books": "x"})

    assert loader.update_book_info(book, now=NOW) is book


def test_deleted_google_id_falls_back_to_search() -> None:
    def responder(url: str, params: Mapping[str, str]) -> FakeResult:
        return VOLUME_GONE if url.endswith("/gone") else _found("Found by search")

    loader = FakeLoader(responder)
    book = loader.update_book_info(_book(google_id="gone"), now=NOW)

    assert book.descriptions == {"google_books": "Found by search"}
    assert book.google_id == "abc123"


@pytest.mark.parametrize(
    "isbn_kwargs, query",
    [
        ({"isbn13": "9780141439471"}, "isbn:9780141439471"),
        ({"isbn": "0141439475"}, "isbn:0141439475"),
        ({"oclc": "12345"}, "oclc:12345"),
    ],
)
def test_identifier_search(isbn_kwargs: Mapping[str, str], query: str) -> None:
    loader = FakeLoader(_always(_found()))
    loader.update_book_info(_book(**isbn_kwargs), now=NOW)

    assert loader.requests[0] == (VOLUMES_URL, {"orderBy": "relevance", "q": query})


def test_not_found_backs_off_exponentially() -> None:
    loader = FakeLoader(_always(NOT_FOUND))
    book = _book()

    expected_delays = [DAY * 2**n for n in range(6)] + [mdl.NOT_FOUND_RETRY_MAX] * 2
    now = NOW
    for failures, expected_delay in enumerate(expected_delays, start=1):
        book = loader.update_book_info(book, now=now)
        status = _status(book)

        assert status.outcome == oh.FetchOutcome.NOT_FOUND
        assert status.failures == failures
        assert status.last_attempt == now
        assert status.retry_after == now + expected_delay
        assert book.metadata_sources is None

        assert not loader.needs_update(book, now=status.retry_after - _SECOND)
        num_requests = len(loader.requests)
        assert loader.update_book_info(book, now=now + DAY / 2) is book
        assert len(loader.requests) == num_requests

        now = status.retry_after
        assert loader.needs_update(book, now=now)


def test_not_found_with_no_search_terms() -> None:
    loader = FakeLoader(_always(AssertionError("Should not be called")))
    book = loader.update_book_info(_book(title=None, authors=None), now=NOW)

    assert _status(book).outcome == oh.FetchOutcome.NOT_FOUND
    assert loader.requests == []


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "Frankenstein; or, The Modern Prometheus"},
        {"authors": ["Mary Wollstonecraft Shelley"]},
        {"isbn13": "9780141439471"},
    ],
)
def test_changing_query_resets_backoff(changes: Mapping[str, Any]) -> None:
    loader = FakeLoader(_always(NOT_FOUND))
    book = loader.update_book_info(_book(), now=NOW)
    book = loader.update_book_info(book, now=_status(book).retry_after)
    assert _status(book).failures == 2

    corrected = attrs.evolve(book, **changes)
    assert loader.needs_update(corrected, now=NOW)

    corrected = loader.update_book_info(corrected, now=NOW)
    assert _status(corrected).failures == 1
    assert _status(corrected).retry_after == NOW + DAY


def test_rejected_query_backs_off() -> None:
    loader = FakeLoader(_always(BAD_REQUEST))
    book = loader.update_book_info(_book(), now=NOW)

    status = _status(book)
    assert status.outcome == oh.FetchOutcome.REJECTED
    assert status.retry_after == NOW + DAY
    assert status.message is not None and "Invalid query" in status.message
    assert loader.available()
    assert loader.unavailable_reason is None


@pytest.mark.parametrize("quota_response", [DAILY_QUOTA_EXCEEDED, LEGACY_DAILY_LIMIT])
def test_daily_quota_stops_requests(
    quota_response: test_updater.FakeResponse, sleeps: Sequence[float]
) -> None:
    loader = FakeLoader(_always(quota_response))
    book = loader.update_book_info(_book(), now=NOW)

    status = _status(book)
    assert status.outcome == oh.FetchOutcome.UNAVAILABLE
    assert status.retry_after is None
    assert status.failures == 0
    assert loader.needs_update(book, now=NOW)

    # Daily quota errors aren't retried, and stop all further requests
    assert len(loader.requests) == 1
    assert sleeps == []
    assert not loader.available()
    assert loader.unavailable_reason is not None

    other_book = loader.update_book_info(_book(id=ID(2), title="Dracula"), now=NOW)
    assert len(loader.requests) == 1
    assert _status(other_book).outcome == oh.FetchOutcome.UNAVAILABLE
    assert other_book.metadata_sources is None


def test_quota_cooldown_expires() -> None:
    loader = FakeLoader(_always(DAILY_QUOTA_EXCEEDED))
    loader.update_book_info(_book(), now=NOW)

    later = datetime.datetime.now(datetime.UTC) + mdl.QUOTA_COOLDOWN
    assert not loader.available(now=later - _SECOND)
    assert loader.available(now=later + _SECOND)


def test_unavailable_does_not_reset_backoff() -> None:
    """A quota error says nothing about the book, so keeps the failure count."""
    loader = FakeLoader(_sequence(NOT_FOUND, NOT_FOUND, DAILY_QUOTA_EXCEEDED))
    book = loader.update_book_info(_book(), now=NOW)
    book = loader.update_book_info(book, now=_status(book).retry_after)
    book = loader.update_book_info(book, now=_status(book).retry_after)

    assert _status(book).outcome == oh.FetchOutcome.UNAVAILABLE
    assert _status(book).failures == 2


@pytest.mark.parametrize(
    "transient_error",
    [
        PER_MINUTE_RATE_LIMIT,
        SERVER_ERROR,
        requests.ConnectionError("Temporary failure in name resolution"),
        requests.Timeout("Timed out"),
    ],
)
def test_transient_errors_are_retried(
    transient_error: FakeResult, sleeps: Sequence[float]
) -> None:
    loader = FakeLoader(_sequence(transient_error, transient_error, _found()))
    book = loader.update_book_info(_book(), now=NOW)

    assert book.descriptions == {"google_books": "A book."}
    assert len(sleeps) == 2
    assert all(0 <= delay <= mdl.REQUEST_RETRY_MAX.total_seconds() for delay in sleeps)
    assert loader.available()


@pytest.mark.parametrize(
    "transient_error",
    [
        PER_MINUTE_RATE_LIMIT,
        SERVER_ERROR,
        requests.ConnectionError("Temporary failure in name resolution"),
    ],
)
def test_persistent_transient_errors_stop_requests(
    transient_error: FakeResult, sleeps: Sequence[float]
) -> None:
    loader = FakeLoader(_always(transient_error))
    book = loader.update_book_info(_book(), now=NOW)

    assert _status(book).outcome == oh.FetchOutcome.UNAVAILABLE
    assert len(loader.requests) == mdl.REQUEST_RETRIES + 1
    assert len(sleeps) == mdl.REQUEST_RETRIES
    assert not loader.available()


@pytest.mark.parametrize(
    "retry_after, expected_sleeps",
    [
        ("7", [7.0]),
        ("3600", []),  # Too long to wait: give up on the request instead
    ],
)
def test_retry_after_header(
    retry_after: str, expected_sleeps: Sequence[float], sleeps: Sequence[float]
) -> None:
    rate_limited = test_updater.FakeResponse(
        status_code=429,
        json_contents=PER_MINUTE_RATE_LIMIT.json(),
        headers={"Retry-After": retry_after},
    )
    loader = FakeLoader(_sequence(rate_limited, _found()))
    loader.update_book_info(_book(), now=NOW)

    assert sleeps == expected_sleeps


class _NotJson(test_updater.FakeResponse):
    def json(self) -> Any:
        raise ValueError("Not JSON")


@pytest.mark.parametrize(
    "response",
    [
        _NotJson(status_code=418),
        test_updater.FakeResponse(status_code=418, json_contents={"error": "teapot"}),
    ],
)
def test_unparseable_error_response(response: test_updater.FakeResponse) -> None:
    loader = FakeLoader(_always(response))
    book = loader.update_book_info(_book(), now=NOW)

    assert _status(book).outcome == oh.FetchOutcome.REJECTED


def test_success_clears_only_own_status() -> None:
    other_status = oh.MetadataFetchStatus(
        outcome=oh.FetchOutcome.NOT_FOUND, last_attempt=NOW, query_key="x"
    )
    loader = FakeLoader(_sequence(NOT_FOUND, _found()))
    book = _book(metadata_fetch_status={"other_source": other_status})
    book = loader.update_book_info(book, now=NOW)
    assert book.metadata_fetch_status is not None
    assert book.metadata_fetch_status.keys() == {"other_source", "google_books"}

    book = loader.update_book_info(book, now=_status(book).retry_after)
    assert book.metadata_fetch_status == {"other_source": other_status}


def _update_all(
    loader: mdl.BookLoader, num_books: int, **kwargs: Any
) -> Mapping[ID, oh.Book]:
    books = {ID(i): _book(id=ID(i), title=f"Book {i}") for i in range(1, num_books + 1)}
    return _update_books(loader, books, **kwargs)


def _update_books(
    loader: mdl.BookLoader, books: Mapping[ID, oh.Book], **kwargs: Any
) -> Mapping[ID, oh.Book]:
    book_updater = updater.BookDatabaseUpdater(".", metadata_loaders=(loader,))
    database = {TableName("books"): dict(books)}
    return book_updater.update_book_metadata(database, **kwargs)["books"]


def test_updater_stops_at_quota(caplog: pytest.LogCaptureFixture) -> None:
    loader = FakeLoader(_sequence(_found("First"), DAILY_QUOTA_EXCEEDED))
    books = _update_all(loader, 5)

    assert books[ID(1)].description == "First"
    assert books[ID(1)].metadata_fetch_status is None
    assert len(loader.requests) == 2
    for book_id in range(2, 6):
        book = books[ID(book_id)]
        assert book.description == ""
        assert _status(book).outcome == oh.FetchOutcome.UNAVAILABLE
        assert book.metadata_sources is None

    assert "google_books unavailable, skipped 3 books" in caplog.text


def test_updater_respects_backoff() -> None:
    loader = FakeLoader(_always(NOT_FOUND))
    books = _update_all(loader, 3)
    assert len(loader.requests) == 3

    _update_books(loader, books)
    assert len(loader.requests) == 3


def test_updater_reload_ignores_backoff() -> None:
    loader = FakeLoader(_sequence(NOT_FOUND, _found("Finally")))
    book = _update(loader, _book())

    book = _update(loader, book, reload_metadata=True)
    assert book.description == "Finally"
