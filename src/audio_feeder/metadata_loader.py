"""
Metadata loading
"""

import datetime
import io
import os
import time
from collections import OrderedDict

import requests

from .config import read_from_config

LOCAL_DATA_SOURCE = "local"


class MetaDataLoader:
    """
    This is a base class for metadata loaders which poll databases for
    relevant metadata.
    """

    #: Minimum delay between requests for the given API endpoint.
    POLL_DELAY = 0.2
    API_ENDPOINT = None
    SOURCE_NAME = None

    def __init__(self, *args, **kwargs):
        self._last_poll = None
        self._poll_delay = datetime.timedelta(seconds=self.POLL_DELAY)

        if self.API_ENDPOINT is None:
            msg = (
                "This is an abstract base class, all subclasses are reuqired"
                " to specify a non-None value for API_ENDPOINT."
            )
            raise NotImplementedError(msg)

        if self.SOURCE_NAME is None:
            msg = (
                "This is an abstract base class, all subclasses are reuqired"
                " to specify a non-None value for SOURCE_NAME."
            )
            raise NotImplementedError(msg)

    def make_request(self, *args, raise_on_early_=False, **kwargs):
        """
        This is a wrapper around the actual request loader, to enforce polling
        delays.

        :param raise_on_early_:
            If true, a :class:`PollDelayIncomplete` exception will be raised if
            a request is made early.
        """
        if self._last_poll is not None:
            time_elapsed = datetime.datetime.utcnow() - self._last_poll

            remaining_time = self._poll_delay - time_elapsed
            remaining_time /= datetime.timedelta(seconds=1)

            if time_elapsed < self._poll_delay:
                if raise_on_early_:
                    raise PollDelayIncomplete(remaining_time)
                else:
                    time.sleep(remaining_time)

        old_poll = self._last_poll
        self._last_poll = datetime.datetime.utcnow()

        try:
            return self.make_request_raw(*args, **kwargs)
        except Exception as e:
            # We'll say last poll only counts if there was no exception.
            self._last_poll = old_poll
            raise e

    def make_request_raw(self, *args, **kwargs):
        return requests.get(*args, **kwargs)


class GoogleBooksLoader(MetaDataLoader):
    """
    Metadata loader pulling from Google Books.
    """

    POLL_DELAY = 1
    API_ENDPOINT = "https://www.googleapis.com/books/v1/volumes"
    SOURCE_NAME = "google_books"

    def get_volume(
        self,
        authors=None,
        title=None,
        isbn=None,
        isbn13=None,
        oclc=None,
        lccn=None,
        google_id=None,
    ):

        if google_id is not None:
            r_json = self.retrieve_volume(google_id)

            if r_json != {}:
                try:
                    return self.parse_volume_metadata(r_json)
                except VolumeInformationMissing:
                    print("No volume with google id {}".format(google_id))
                    print("Using other information for {} - {}".format(authors, title))

        # If we don't have a google_id, let's try to use one of the identifiers.
        identifiers = OrderedDict(isbn13=isbn13, isbn=isbn, oclc=oclc, lccn=lccn)

        # Try pulling the data based on the first existing identifier
        for id_type, identifier in identifiers.items():
            if identifier is not None:
                if id_type == "isbn13":
                    id_type = "isbn"

                query_list = [id_type + ":" + str(identifier)]

                r_json = self.retrieve_search_results(query_list)
                total_items = r_json.get("totalItems", 0)
                if total_items >= 1:
                    # In the unlikely event that there's more than one, we'll
                    # just pick the first one
                    return self.parse_volume_metadata(r_json["items"][0])

        query_list = []
        if authors is not None:
            for author in authors:
                query_list.append("inauthor:" + author)

        if title is not None:
            query_list.append("intitle:" + title)

        r_json = self.retrieve_search_results(query_list)

        total_items = r_json.get("totalItems", 0)
        if total_items >= 1:
            return self.parse_volume_metadata(r_json["items"][0])
        else:
            return None

    def retrieve_search_results(self, query_list, **params):
        params_base = {"orderBy": "relevance"}
        params_base.update(params)
        params = params_base

        query_text = "+".join(query_list)
        params["q"] = query_text

        # Not catching exceptions for the moment.
        r = self.make_request(self.API_ENDPOINT, params=params)

        return r.json()

    def retrieve_volume(self, google_id):
        r = self.make_request(os.path.join(self.API_ENDPOINT, google_id))

        return r.json()

    def make_request(self, *args, **kwargs):
        API_KEY = read_from_config("google_api_key")
        if API_KEY is not None:
            if "params" not in kwargs:
                kwargs["params"] = {}

            kwargs["params"]["key"] = API_KEY

        return super().make_request(*args, **kwargs)

    def parse_volume_metadata(self, j_item):
        """
        Parse the volume metadata from the response JSON.
        """
        out = {}
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

    def update_book_info(self, book_obj, overwrite_existing=False):
        if book_obj.metadata_sources is None:
            book_obj.metadata_sources = []

        if not overwrite_existing and self.SOURCE_NAME in book_obj.metadata_sources:
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

        md = self.get_volume(**get_volume_params)
        if md is None:
            return book_obj

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
                setattr(book_obj, key, md[key])

        # These are keys where Google Books wins out
        overwrite_keys = ("google_id",)
        for key in overwrite_keys:
            new_val = md.get(key, None)
            if new_val is not None:
                setattr(book_obj, key, new_val)

        # Add a Google Books description if it doesn't exist already.
        if book_obj.descriptions is None:
            book_obj.descriptions = {}

        book_obj.descriptions[self.SOURCE_NAME] = md["description"]

        # Append any tags that aren't in there already
        if book_obj.tags is None:
            book_obj.tags = []

        for category in md["categories"]:
            if category not in book_obj.tags:
                book_obj.tags.append(category)

        if book_obj.cover_images is None:
            book_obj.cover_images = {}

        if self.SOURCE_NAME not in book_obj.cover_images:
            book_obj.cover_images[self.SOURCE_NAME] = {}

        book_obj.cover_images[self.SOURCE_NAME].update(md["image_link"])

        book_obj.metadata_sources.append(self.SOURCE_NAME)

        return book_obj

    @classmethod
    def retrieve_best_image(cls, cover_images):
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


class PollDelayIncomplete(Exception):
    def __init__(self, *args, time_remaining=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.time_remaining = time_remaining


class VolumeInformationMissing(KeyError):
    pass
