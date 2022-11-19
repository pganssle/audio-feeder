"""
RSS Feed generators
"""
import os
import re
import typing
import urllib.parse
from datetime import timedelta
from urllib.parse import urljoin
from xml.sax import saxutils

from . import database_handler as dh
from . import directory_parser as dp
from .config import read_from_config
from .hash_utils import hash_random
from .resolver import Resolver

_T = typing.TypeVar("_T")


def load_feed_items(entry_obj, resolver=None, loader=dp.AudiobookLoader):
    """
    Creates feed items from a directory.

    :param entry_obj:
        A :class:`object_handlers.Entry` object.

    :param loader:
        A subclass of :class:`directory_parser.BaseAudioLoader`.

    :return:
        Returns a list of feed items for use with the RSS templates.

        .. note::
            The "url" parameter of each feed item will be relative to the static
            media url - this should be modified on the fly when actually
            generating the rss files.
    """
    if resolver is None:
        resolver = Resolver()

    audio_dir = resolver.resolve_media(entry_obj.path)
    if not os.path.exists(audio_dir.path):
        raise ItemNotFoundError("Could not find item: {}".format(audio_dir))

    pub_date = entry_obj.date_added
    data_obj = dh.get_database_table(entry_obj.table)[entry_obj.data_id]

    audio_files = loader.audio_files(audio_dir.path)

    feed_items = []
    for ii, audio_file in enumerate(sorted(audio_files)):
        feed_item = {}

        relpath = os.path.relpath(audio_file, audio_dir.path)
        relpath = urllib.parse.quote(relpath)

        url = _urljoin_dir(audio_dir.url, relpath)

        file_size = os.path.getsize(audio_file)
        feed_item["fname"] = os.path.split(audio_file)[1]
        feed_item["size"] = file_size
        feed_item["url"] = url
        feed_item["pubdate"] = pub_date + timedelta(minutes=ii)
        feed_item["desc"] = data_obj.description or ""
        if entry_obj.file_hashes and audio_file in entry_obj.file_hashes:
            file_hash = entry_obj.file_hashes[audio_file].hex()
        else:
            file_hash = hash_random(audio_file, entry_obj.hashseed).hex()
        feed_item["guid"] = file_hash

        feed_items.append({k: wrap_field(v) for k, v in feed_item.items()})

    return feed_items


html_chars = re.compile("<[^>]+>")


def wrap_field(field: _T) -> _T:
    """
    Given a field, detect if it has special characters <, > or & and if so
    wrap it in a CDATA field.
    """
    if not isinstance(field, str):
        return field

    if html_chars.search(field):
        out: str = "<![CDATA[" + field + "]]>"
    else:
        # If there's already escaped data like &amp;, I want to unescape it
        # first, so I can re-escape *everything*
        unescaped = saxutils.unescape(field)

        out = saxutils.escape(unescaped)

    # This is a bug in mypy: https://github.com/python/cpython/issues/99272
    return typing.cast(_T, out)


def _urljoin_dir(dir_, fragment):
    if not dir_.endswith("/"):
        dir_ += "/"

    return urljoin(dir_, fragment)


class ItemNotFoundError(ValueError):
    pass
