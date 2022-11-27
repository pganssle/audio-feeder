"""
Metadata loading
"""

import abc
import copy
import datetime
import functools
import io
import logging
import os
import time
import typing

import attrs
import requests

from . import object_handler as oh
from .config import read_from_config

LOCAL_DATA_SOURCE: typing.Final[str] = "local"
_SECONDS: typing.Final[datetime.timedelta] = datetime.timedelta(seconds=1)


class MetaDataLoader(metaclass=abc.ABCMeta):
    """
    This is a base class for metadata loaders which poll databases for
    relevant metadata.
    """

    def __init__(
        self,
        poll_delay: typing.Union[float, datetime.timedelta] = 0.2,
    ):
        self._last_poll: typing.Optional[datetime.datetime] = None
        self._poll_delay = (
            datetime.timedelta(seconds=poll_delay)
            if not isinstance(poll_delay, datetime.timedelta)
            else poll_delay
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
            time_elapsed = (
                datetime.datetime.now(datetime.timezone.utc) - self._last_poll
            )

            remaining_time = (self._poll_delay - time_elapsed) / _SECONDS

            if time_elapsed < self._poll_delay:
                if raise_on_early_:
                    raise PollDelayIncomplete(remaining_time)

                time.sleep(remaining_time)

        old_poll = self._last_poll
        self._last_poll = datetime.datetime.now(datetime.timezone.utc)

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
        valid_identifiers: typing.Sequence[str] = (),
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._valid_identifiers = frozenset(valid_identifiers)

    @functools.cached_property
    def valid_identifiers(self) -> typing.Collection[str]:
        return (
            "isbn",
            "isbn13",
            "oclc",
            "oclc",
            "lccn",
            "google_id",
        )

    def retrieve_volume(self, google_id):
        r = self.make_request(os.path.join(self.api_endpoint, google_id))

        return r.json()

    @abc.abstractmethod
    def update_book_info(
        self, book_obj: oh.Book, overwrite_existing: bool = False
    ) -> oh.Book:
        # TODO: Implement in a generic way?
        raise NotImplementedError

    @abc.abstractmethod
    def retrieve_best_image(
        self, cover_images: typing.Mapping[str, str]
    ) -> typing.Union[
        typing.Tuple[typing.BinaryIO, str, str], typing.Tuple[None, None, None]
    ]:
        """
        Given a dictionary of cover image URLs, this retrieves the largest
        available image.
        """
        raise NotImplementedError


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

    def update_book_info(
        self, book_obj: oh.Book, overwrite_existing: bool = False
    ) -> oh.Book:
        if book_obj.metadata_sources is None:
            book_obj.metadata_sources = []

        if not overwrite_existing and self.source_name in book_obj.metadata_sources:
            return book_obj

        get_volume_params = {
            k: getattr(book_obj, k, None)
            for k in (
                "title",
                "authors",
                "isbn",
                "isbn13",
                "oclc",
                "lccn",
                "issn",
                "google_id",
            )
        }

        get_volume_params = {
            k: v for k, v in get_volume_params.items() if v is not None
        }

        try:
            md = self._get_volume(**get_volume_params)
            if md is None:
                return book_obj
        except BookNotFound:
            logging.error(
                "Could not load metadata for book %d: %s - %s",
                book_obj.id,
                " & ".join(book_obj.authors) if book_obj.authors else None,
                book_obj.title,
            )
            return book_obj

        new_book_keys: typing.MutableMapping[str, typing.Any] = {}

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

        # Add a Google Books description if it doesn't exist already.
        if book_obj.descriptions is None and "descriptions" not in new_book_keys:
            new_book_keys["descriptions"] = {self.source_name: md["description"]}

        # Append any tags that aren't in there already
        existing_book_tags = set(book_obj.tags) if book_obj.tags is not None else set()
        new_tags = set(md["categories"]) - existing_book_tags

        if new_tags:
            new_book_keys["tags"] = sorted(existing_book_tags & new_tags)

        new_book_keys["cover_images"] = (
            copy.deepcopy(book_obj.cover_images)
            if book_obj.cover_images is not None
            else {}
        )
        new_book_keys["cover_images"].setdefault(self.source_name, {}).update(
            md["image_link"]
        )

        new_book_keys["metadata_sources"] = list(book_obj.metadata_sources)
        new_book_keys["metadata_sources"].append(self.source_name)

        return attrs.evolve(book_obj, **new_book_keys)

    def retrieve_best_image(
        self, cover_images: typing.Mapping[str, str]
    ) -> typing.Union[
        typing.Tuple[typing.BinaryIO, str, str], typing.Tuple[None, None, None]
    ]:
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

    # Encodes the schema for the JSON response, found here:
    # https://developers.google.com/books/docs/v1/reference/volumes#resource
    #
    # We are (mostly) specifying just the parts we care about
    class _QueryResponse(typing.TypedDict, total=False):
        items: typing.Sequence["_VolumeResponse"]
        totalItems: int

    class _VolumeResponse(typing.TypedDict, total=False):
        kind: str
        id: str
        etag: str
        selfLink: str
        volumeInfo: "_VolumeInfo"

    class _VolumeInfo(typing.TypedDict, total=False):
        title: str
        subtitle: str
        authors: typing.Sequence[str]
        industryIdentifiers: typing.Sequence["_IndustryIdentifier"]
        publisher: str
        publishedDate: str
        description: str
        pageCount: int
        categories: typing.Sequence[str]
        imageLinks: "_ImageLink"
        language: str

    class _IndustryIdentifier(typing.TypedDict, total=False):
        type: str
        identifier: str

    class _ImageLink(typing.TypedDict, total=False):
        smallThumbnail: str
        thumbnail: str
        small: str
        medium: str
        large: str
        extraLarge: str

    @functools.cached_property
    def _google_api_key(self) -> typing.Optional[str]:
        return read_from_config("google_api_key")

    def _get_volume(
        self,
        authors: typing.Optional[typing.Sequence[str]] = None,
        title: typing.Optional[str] = None,
        **identifiers: typing.Optional[str],
    ) -> typing.Mapping[str, typing.Any]:
        if extra_identifiers := identifiers.keys() - self.valid_identifiers:
            raise TypeError(f"Unknown identifiers: {','.join(extra_identifiers)}")

        if (google_id := identifiers.pop("google_id", None)) is not None:
            r_json = self.retrieve_volume(google_id)

            if r_json != {}:
                try:
                    return self._parse_volume_metadata(r_json)
                except VolumeInformationMissing:
                    logging.info(f"No volume with google id %s", google_id)
                    logging.info(f"Using other information for %s - %s", authors, title)

        # Try pulling the data based on the first existing identifier
        for id_type in ["isbn13", "isbn", "oclc", "lccn"]:
            if id_type in identifiers:
                identifier = identifiers[id_type]
                if id_type == "isbn13":
                    id_type = "isbn"

                query_list: typing.List[str] = [f"{id_type}:{identifier}"]

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

        r_json = self._retrieve_search_results(query_list)

        total_items = r_json.get("totalItems", 0)
        if total_items >= 1:
            return self._parse_volume_metadata(r_json["items"][0])

        raise BookNotFound("No items found")

    def _parse_volume_metadata(
        self, j_item: _VolumeResponse
    ) -> typing.Mapping[str, typing.Any]:
        """
        Parse the volume metadata from the response JSON.
        """
        out: typing.MutableMapping[str, typing.Any] = {}
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
        self, query_list: typing.Sequence[str], **params
    ) -> _VolumeResponse:
        params_base = {"orderBy": "relevance"}
        params_base.update(params)
        params = params_base

        query_text = "+".join(query_list)
        params["q"] = query_text

        # Not catching exceptions for the moment.
        r = self.make_request(self.api_endpoint, params=params)

        return r.json()


class PollDelayIncomplete(Exception):
    def __init__(self, *args, time_remaining=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.time_remaining = time_remaining


class BookNotFound(ValueError):
    """Raised when a book is not available."""


class VolumeInformationMissing(KeyError):
    pass
