"""
Metadata loading
"""

from __future__ import annotations

import abc
import copy
import datetime
import functools
import hashlib
import io
import json
import logging
import os
import random
import time
from collections.abc import Collection, Mapping, MutableMapping, Sequence, Set
from typing import Any, BinaryIO, Final, TypedDict

import attrs
import requests

from . import object_handler as oh
from .config import (
    MetadataRetryConfig,
    metadata_retry_config,
    read_from_config,
)

LOCAL_DATA_SOURCE: Final[str] = "local"
_SECONDS: Final[datetime.timedelta] = datetime.timedelta(seconds=1)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class MetaDataLoader(metaclass=abc.ABCMeta):
    """
    This is a base class for metadata loaders which poll databases for
    relevant metadata.
    """

    def __init__(
        self,
        poll_delay: float | datetime.timedelta = 0.2,
    ):
        self._last_poll: datetime.datetime | None = None
        self._poll_delay = (
            datetime.timedelta(seconds=poll_delay)
            if not isinstance(poll_delay, datetime.timedelta)
            else poll_delay
        )
        self._unavailable_until: datetime.datetime | None = None
        self._unavailable_reason: str | None = None

    def available(self) -> bool:
        """Whether this source can currently be queried.

        After a quota error or repeated server / network errors, the source is
        marked unavailable for a cooldown period so that we stop sending it
        requests that are going to fail anyway.
        """
        if self._unavailable_until is None:
            return True

        return _now() >= self._unavailable_until

    @property
    def unavailable_reason(self) -> str | None:
        """The error that made this source unavailable, if it is unavailable."""
        if self.available():
            return None
        return self._unavailable_reason

    @functools.cached_property
    def retry_config(self) -> MetadataRetryConfig:
        """When to retry after failures, from the ``metadata_retry`` setting."""
        return metadata_retry_config(self.source_name)

    def _mark_unavailable(self, error: ServiceUnavailable) -> None:
        cooldown = (
            self.retry_config.quota_cooldown
            if isinstance(error, QuotaExceeded)
            else self.retry_config.unavailable_cooldown
        )
        self._unavailable_until = _now() + cooldown
        self._unavailable_reason = str(error)
        logging.warning(
            "Not querying %s until %s: %s",
            self.source_name,
            # Displayed in local time
            self._unavailable_until.astimezone(None).isoformat(
                sep=" ", timespec="seconds"
            ),
            error,
        )

    @property
    @abc.abstractmethod
    def api_endpoint(self) -> str:
        raise NotImplementedError  # pragma: nocover

    @property
    @abc.abstractmethod
    def source_name(self) -> str:
        raise NotImplementedError

    def make_request(
        self, *args, raise_on_early_: bool = False, **kwargs
    ) -> requests.Response:
        """
        This is a wrapper around the actual request loader, to enforce polling
        delays.

        :param raise_on_early_:
            If true, a :class:`PollDelayIncomplete` exception will be raised if
            a request is made early.
        """
        if self._last_poll is not None:
            time_elapsed = datetime.datetime.now(datetime.UTC) - self._last_poll

            remaining_time = (self._poll_delay - time_elapsed) / _SECONDS

            if time_elapsed < self._poll_delay:
                if raise_on_early_:
                    raise PollDelayIncomplete(remaining_time)

                time.sleep(remaining_time)

        old_poll = self._last_poll
        self._last_poll = datetime.datetime.now(datetime.UTC)

        try:
            return self.make_request_raw(*args, **kwargs)
        except Exception:
            # We'll say last poll only counts if there was no exception.
            self._last_poll = old_poll
            raise

    def make_request_raw(self, *args, **kwargs) -> requests.Response:
        return requests.get(*args, **kwargs)


class BookLoader(MetaDataLoader):
    """
    Abstract base class for loaders pulling from a book.
    """

    def __init__(
        self,
        *args,
        valid_identifiers: Sequence[str] = (),
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._valid_identifiers = frozenset(valid_identifiers)

    @functools.cached_property
    def valid_identifiers(self) -> Collection[str]:
        return (
            "isbn",
            "isbn13",
            "oclc",
            "oclc",
            "lccn",
            "google_id",
        )

    def needs_update(self, book_obj: oh.Book) -> bool:
        """Whether metadata should be (re-)fetched from this source.

        This is false if the metadata has already been retrieved, or if a
        recent attempt for the same query failed and we are still waiting to
        retry it.
        """
        if not self._missing_metadata(book_obj):
            return False

        status = (book_obj.metadata_fetch_status or {}).get(self.source_name, None)
        if (
            status is not None
            and status.retry_after is not None
            and status.query_key == self._query_key(book_obj)
        ):
            return _now() >= status.retry_after

        return True

    def _missing_metadata(self, book_obj: oh.Book) -> bool:
        return self.source_name not in (book_obj.metadata_sources or ())

    def _query_params(self, book_obj: oh.Book) -> Mapping[str, Any]:
        """The information about a book that is used to look it up."""
        params = {
            k: getattr(book_obj, k, None)
            for k in ("title", "authors", "issn") + tuple(self.valid_identifiers)
        }
        return {k: v for k, v in params.items() if v is not None}

    def _query_key(self, book_obj: oh.Book) -> str:
        params_json = json.dumps(self._query_params(book_obj), sort_keys=True)
        return hashlib.sha256(params_json.encode("utf-8")).hexdigest()[0:16]

    def _record_failure(
        self,
        book_obj: oh.Book,
        outcome: oh.FetchOutcome,
        message: str,
    ) -> oh.Book:
        """Return a copy of ``book_obj`` with a failed fetch attempt recorded.

        NOT_FOUND and REJECTED failures say something about the book (or how
        we're looking it up), so they schedule a retry with exponential
        backoff. UNAVAILABLE failures say nothing about the book, so they can
        be retried as soon as the source is available again.
        """
        now = _now()
        query_key = self._query_key(book_obj)
        fetch_status = dict(book_obj.metadata_fetch_status or {})
        previous = fetch_status.get(self.source_name, None)
        previous_failures = (
            previous.failures
            if previous is not None and previous.query_key == query_key
            else 0
        )

        if outcome == oh.FetchOutcome.UNAVAILABLE:
            failures = previous_failures
            retry_after = None
        else:
            failures = previous_failures + 1
            retry_after = now + min(
                self.retry_config.not_found_retry_base * 2 ** (failures - 1),
                self.retry_config.not_found_retry_max,
            )

        fetch_status[self.source_name] = oh.MetadataFetchStatus(
            outcome=outcome,
            last_attempt=now,
            query_key=query_key,
            failures=failures,
            retry_after=retry_after,
            message=message,
        )
        return attrs.evolve(book_obj, metadata_fetch_status=fetch_status)

    def _cleared_fetch_status(
        self, book_obj: oh.Book
    ) -> Mapping[str, oh.MetadataFetchStatus] | None:
        if book_obj.metadata_fetch_status is None:
            return None

        return {
            source: status
            for source, status in book_obj.metadata_fetch_status.items()
            if source != self.source_name
        } or None

    @abc.abstractmethod
    def update_book_info(
        self,
        book_obj: oh.Book,
        overwrite_existing: bool = False,
    ) -> oh.Book:
        """Fetch metadata for ``book_obj``, returning an updated copy.

        If the fetch fails, the failure is recorded in the returned book's
        ``metadata_fetch_status`` rather than raised.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def retrieve_best_image(
        self, cover_images: Mapping[str, str]
    ) -> tuple[BinaryIO, str, str] | tuple[None, None, None]:
        """
        Given a dictionary of cover image URLs, this retrieves the largest
        available image.
        """
        raise NotImplementedError


# Encodes the schema for the JSON response, found here:
# https://developers.google.com/books/docs/v1/reference/volumes#resource
#
# We are (mostly) specifying just the parts we care about
class _QueryResponse(TypedDict, total=False):
    items: Sequence[_VolumeResponse]
    totalItems: int


class _VolumeResponse(TypedDict, total=False):
    kind: str
    id: str
    etag: str
    selfLink: str
    volumeInfo: _VolumeInfo


class _VolumeInfo(TypedDict, total=False):
    title: str
    subtitle: str
    authors: Sequence[str]
    industryIdentifiers: Sequence[_IndustryIdentifier]
    publisher: str
    publishedDate: str
    description: str
    pageCount: int
    categories: Sequence[str]
    imageLinks: _ImageLink
    language: str


class _IndustryIdentifier(TypedDict, total=False):
    type: str
    identifier: str


class _ImageLink(TypedDict, total=False):
    smallThumbnail: str
    thumbnail: str
    small: str
    medium: str
    large: str
    extraLarge: str


class GoogleBooksLoader(BookLoader):
    def __init__(self, *args, **kwargs):
        if "poll_delay" not in kwargs:
            kwargs["poll_delay"] = _SECONDS
        super().__init__(*args, **kwargs)

    @property
    def api_endpoint(self) -> str:
        return "https://www.googleapis.com/books/v1/volumes"

    @property
    def source_name(self) -> str:
        return "google_books"

    def make_request(self, *args, **kwargs):
        if self._google_api_key is not None:
            if "params" not in kwargs:
                kwargs["params"] = {}

            kwargs["params"]["key"] = self._google_api_key

        return super().make_request(*args, **kwargs)

    def _get_json(self, url: str, params: Mapping[str, str] | None = None) -> Any:
        """Make a request to the API and return the decoded response body.

        Rate limit and server errors are retried with exponential backoff; if
        they persist, or if the daily quota is exhausted, this source is marked
        unavailable and :class:`ServiceUnavailable` is raised. Other errors
        raise :class:`RequestFailed`.
        """
        attempt = 0
        while True:
            if not self.available():
                raise ServiceUnavailable(
                    f"{self.source_name} is unavailable: {self._unavailable_reason}"
                )

            try:
                r = self.make_request(
                    url,
                    params=dict(params or {}),
                    timeout=self.retry_config.request_timeout / _SECONDS,
                )
            except requests.RequestException as e:
                error: MetadataServiceError = ServiceUnavailable(
                    f"Error connecting to {self.source_name}: {e}"
                )
            else:
                if r.status_code == 200:
                    return r.json()
                error = _classify_google_error(r)

            if not isinstance(error, ServiceUnavailable):
                raise error

            retry_delay = self._retry_delay(error, attempt)
            if retry_delay is None:
                self._mark_unavailable(error)
                raise error

            logging.info(
                "Error from %s, retrying in %0.1fs: %s",
                self.source_name,
                retry_delay / _SECONDS,
                error,
            )
            time.sleep(retry_delay / _SECONDS)
            attempt += 1

    def _retry_delay(
        self, error: ServiceUnavailable, attempt: int
    ) -> datetime.timedelta | None:
        """How long to wait before retrying a request, or None to give up."""
        config = self.retry_config
        if attempt >= config.request_retries:
            return None

        if isinstance(error, QuotaExceeded) and error.daily:
            # No point retrying until tomorrow
            return None

        if error.retry_after is not None:
            if error.retry_after > config.request_retry_max:
                return None
            return error.retry_after

        # Exponential backoff with "full jitter"
        return random.uniform(0, 1) * min(
            config.request_retry_base * 2**attempt, config.request_retry_max
        )

    def _missing_metadata(self, book_obj: oh.Book) -> bool:
        # A bug in earlier versions dropped the description from successful
        # fetches when a previous attempt had failed; those books have this
        # source in `metadata_sources`, but no entry in `descriptions`.
        # Successful fetches always record a description (even if it's None).
        return super()._missing_metadata(book_obj) or (
            self.source_name not in (book_obj.descriptions or {})
        )

    def update_book_info(
        self,
        book_obj: oh.Book,
        overwrite_existing: bool = False,
    ) -> oh.Book:
        if not overwrite_existing and not self.needs_update(book_obj):
            return book_obj

        if not self.available():
            return self._record_failure(
                book_obj,
                oh.FetchOutcome.UNAVAILABLE,
                f"Not attempted: {self._unavailable_reason}",
            )

        authors = " & ".join(book_obj.authors) if book_obj.authors else None
        book_desc = f"{book_obj.id}: {authors} - {book_obj.title}"

        try:
            md = self._get_volume(**self._query_params(book_obj))
        except BookNotFound as e:
            logging.warning(
                "Could not find %s for book %s", self.source_name, book_desc
            )
            return self._record_failure(book_obj, oh.FetchOutcome.NOT_FOUND, str(e))
        except RequestFailed as e:
            logging.error(
                "%s rejected query for book %s: %s", self.source_name, book_desc, e
            )
            return self._record_failure(book_obj, oh.FetchOutcome.REJECTED, str(e))
        except ServiceUnavailable as e:
            logging.warning(
                "Could not load metadata from %s for book %s: %s",
                self.source_name,
                book_desc,
                e,
            )
            return self._record_failure(book_obj, oh.FetchOutcome.UNAVAILABLE, str(e))

        new_book_keys: MutableMapping[str, Any] = {}

        # These are keys where the value is set only if it didn't exist before.
        keep_existing_keys = (
            "authors",
            "title",
            "isbn",
            "isbn13",
            "issn",
            "pages",
            "pub_date",
            "publisher",
            "language",
        )

        for key in keep_existing_keys:
            if getattr(book_obj, key, None) is None and key in md:
                new_book_keys[key] = md[key]

        # These are keys where Google Books wins out
        overwrite_keys = ("google_id",)
        for key in overwrite_keys:
            new_val = md.get(key, None)
            if new_val is not None:
                new_book_keys[key] = new_val

        # Record the Google Books description, even if it is None, so that we
        # know it has been retrieved.
        descriptions = dict(book_obj.descriptions or {})
        if overwrite_existing or self.source_name not in descriptions:
            descriptions[self.source_name] = md["description"]
        new_book_keys["descriptions"] = descriptions

        # Append any tags that aren't in there already
        existing_book_tags: set[str] = (
            set(book_obj.tags) if book_obj.tags is not None else set()
        )
        new_tags = set(md["categories"]) - existing_book_tags

        if new_tags:
            new_book_keys["tags"] = sorted(existing_book_tags & new_tags)

        cover_images: dict[str, Any] = (
            dict(copy.deepcopy(book_obj.cover_images))
            if book_obj.cover_images is not None
            else {}
        )
        cover_images.setdefault(self.source_name, {}).update(md["image_link"])
        new_book_keys["cover_images"] = cover_images

        metadata_sources = list(book_obj.metadata_sources or ())
        if self.source_name not in metadata_sources:
            metadata_sources.append(self.source_name)
        new_book_keys["metadata_sources"] = metadata_sources
        new_book_keys["metadata_fetch_status"] = self._cleared_fetch_status(book_obj)

        return attrs.evolve(book_obj, **new_book_keys)

    def retrieve_best_image(
        self, cover_images: Mapping[str, str]
    ) -> tuple[BinaryIO, str, str] | tuple[None, None, None]:
        """
        Given a dictionary of cover image URLs, this retrieves the largest
        available image.
        """
        sizes = [
            "extraLarge",
            "large",
            "medium",
            "small",
            "thumbnail",
            "smallthumbnail",
        ]

        for size in sizes:
            if size in cover_images:
                # Download the data
                r = requests.get(cover_images[size])
                if r.status_code != 200:
                    continue

                r.raw.decode_content = True

                fl = io.BytesIO(r.content)

                return (fl, cover_images[size], size)

        return None, None, None

    @functools.cached_property
    def _google_api_key(self) -> str | None:
        return read_from_config("google_api_key")

    def _get_volume(
        self,
        authors: Sequence[str] | None = None,
        title: str | None = None,
        **identifiers: str | None,
    ) -> Mapping[str, Any]:
        if extra_identifiers := identifiers.keys() - self.valid_identifiers:
            raise TypeError(f"Unknown identifiers: {','.join(extra_identifiers)}")

        if (google_id := identifiers.pop("google_id", None)) is not None:
            volume_json: _VolumeResponse
            try:
                volume_json = self._get_json(os.path.join(self.api_endpoint, google_id))
            except RequestFailed as e:
                # Most likely a 404 because the volume no longer exists
                logging.info("Could not retrieve google id %s: %s", google_id, e)
                volume_json = {}

            if volume_json != {}:
                try:
                    return self._parse_volume_metadata(volume_json)
                except VolumeInformationMissing:
                    logging.info("No volume with google id %s", google_id)
                    logging.info("Using other information for %s - %s", authors, title)

        # Try pulling the data based on the first existing identifier
        for id_type in ["isbn13", "isbn", "oclc", "lccn"]:
            if id_type in identifiers:
                identifier = identifiers[id_type]
                if id_type == "isbn13":
                    id_type = "isbn"

                query_list: list[str] = [f"{id_type}:{identifier}"]

                r_json = self._retrieve_search_results(query_list)
                total_items = r_json.get("totalItems", 0)
                if total_items >= 1:
                    # In the unlikely event that there's more than one, we'll
                    # just pick the first one
                    return self._parse_volume_metadata(r_json["items"][0])

        query_list = []
        if authors is not None:
            for author in authors:
                query_list.append("inauthor:" + author)

        if title is not None:
            query_list.append("intitle:" + title)

        if not query_list:
            raise BookNotFound("No title, authors or identifiers to search for")

        r_json = self._retrieve_search_results(query_list)

        total_items = r_json.get("totalItems", 0)
        if total_items >= 1:
            return self._parse_volume_metadata(r_json["items"][0])

        raise BookNotFound("No items found")

    def _parse_volume_metadata(self, j_item: _VolumeResponse) -> Mapping[str, Any]:
        """
        Parse the volume metadata from the response JSON.
        """
        out: MutableMapping[str, Any] = {}
        try:
            v_info = j_item["volumeInfo"]
        except KeyError as e:
            raise VolumeInformationMissing("Missing volume information") from e

        out["google_id"] = j_item["id"]

        out["title"] = v_info.get("title", None)
        out["authors"] = v_info.get("authors", None)
        out["subtitle"] = v_info.get("subtitle", None)
        out["description"] = v_info.get("description", None)
        out["pub_date"] = v_info.get("publishedDate", None)
        out["publisher"] = v_info.get("publisher", None)

        for identifier_dict in v_info.get("industryIdentifiers", []):
            if identifier_dict["type"] == "ISBN_13":
                out["isbn13"] = identifier_dict["identifier"]
            elif identifier_dict["type"] == "ISBN_10":
                out["isbn13"] = identifier_dict["identifier"]
            elif identifier_dict["type"] == "ISSN":
                out["issn"] = identifier_dict["identifier"]

        out["pages"] = v_info.get("pageCount", None)
        out["language"] = v_info.get("language", None)

        out["image_link"] = v_info.get("imageLinks", {})

        out["categories"] = v_info.get("categories", [])
        out["categories"] = [x.lower() for x in out["categories"]]

        return out

    def _retrieve_search_results(
        self, query_list: Sequence[str], **params
    ) -> _QueryResponse:
        params_base = {"orderBy": "relevance"}
        params_base.update(params)
        params = params_base

        query_text = "+".join(query_list)
        params["q"] = query_text

        return self._get_json(self.api_endpoint, params=params)


def _classify_google_error(r: requests.Response) -> MetadataServiceError:
    """Convert an error response from a Google API into an exception.

    Google APIs return errors in this format (with ``errors`` and ``details``
    both optional):

        {"error": {"code": 429, "message": "Quota exceeded ...",
                   "errors": [{"reason": "rateLimitExceeded", ...}],
                   "status": "RESOURCE_EXHAUSTED",
                   "details": [{"reason": "RATE_LIMIT_EXCEEDED",
                                "metadata": {"quota_limit": "defaultPerDayPerProject",
                                             ...}}]}}
    """
    try:
        error_json = r.json().get("error", {})
        if not isinstance(error_json, dict):
            error_json = {}
    except (ValueError, AttributeError):
        error_json = {}

    message = f"HTTP {r.status_code}: {error_json.get('message', 'unknown error')}"

    reasons = {e.get("reason", "") for e in error_json.get("errors", ())}
    quota_limits = set()
    for detail in error_json.get("details", ()):
        reasons.add(detail.get("reason", ""))
        quota_limits.add(detail.get("metadata", {}).get("quota_limit", ""))

    is_quota_error = (
        r.status_code == 429
        or error_json.get("status", None) == "RESOURCE_EXHAUSTED"
        or bool(reasons & _GOOGLE_QUOTA_REASONS)
    )

    if is_quota_error:
        daily = "dailyLimitExceeded" in reasons or any(
            "perday" in limit.lower() for limit in quota_limits
        )
        return QuotaExceeded(
            message, daily=daily, retry_after=_parse_retry_after(r.headers)
        )

    if r.status_code in (408, 500, 502, 503, 504):
        return ServiceUnavailable(message, retry_after=_parse_retry_after(r.headers))

    return RequestFailed(message, status_code=r.status_code)


# Error reasons that mean a quota or rate limit was exceeded. Newer APIs give
# the reason in an ErrorInfo detail (https://google.aip.dev/193), and older
# ones in the `errors` list; the Books API has no list of its own, but these
# are shared by Google's APIs, e.g. as listed for the Drive API in
# https://developers.google.com/drive/api/guides/handle-errors
_GOOGLE_QUOTA_REASONS: Final[Set[str]] = frozenset(
    (
        "dailyLimitExceeded",
        "quotaExceeded",
        "rateLimitExceeded",
        "userRateLimitExceeded",
        "RATE_LIMIT_EXCEEDED",
        "RESOURCE_EXHAUSTED",
    )
)


def _parse_retry_after(
    headers: Mapping[str, str],
) -> datetime.timedelta | None:
    if (retry_after := headers.get("Retry-After", None)) is None:
        return None

    # Retry-After may also be an HTTP date, but Google uses seconds.
    try:
        return datetime.timedelta(seconds=int(retry_after))
    except ValueError:
        logging.warning("Ignoring unrecognized Retry-After header: %r", retry_after)
        return None


class MetadataServiceError(Exception):
    """Base class for errors from a metadata service."""


class ServiceUnavailable(MetadataServiceError):
    """The service cannot currently be queried; this is not specific to a book."""

    def __init__(self, *args, retry_after: datetime.timedelta | None = None) -> None:
        super().__init__(*args)
        self.retry_after = retry_after


class QuotaExceeded(ServiceUnavailable):
    """The API quota has been exhausted."""

    def __init__(
        self,
        *args,
        daily: bool = False,
        retry_after: datetime.timedelta | None = None,
    ) -> None:
        super().__init__(*args, retry_after=retry_after)
        self.daily = daily


class RequestFailed(MetadataServiceError):
    """The service rejected a specific request."""

    def __init__(self, *args, status_code: int) -> None:
        super().__init__(*args)
        self.status_code = status_code


class PollDelayIncomplete(Exception):
    def __init__(self, *args, time_remaining=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.time_remaining = time_remaining


class BookNotFound(ValueError):
    """Raised when a book is not available."""


class VolumeInformationMissing(KeyError):
    pass
