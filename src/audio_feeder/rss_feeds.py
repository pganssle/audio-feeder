"""
RSS Feed generators
"""
import hashlib
import math
import os
import random
import re
import typing
import urllib.parse
from datetime import timedelta
from urllib.parse import urljoin
from xml.sax import saxutils

from . import database_handler as dh
from . import directory_parser as dp
from .config import read_from_config
from .resolver import Resolver

_T = typing.TypeVar("_T")


def hash_random(
    fpath, hashseed, hash_amt=2**20, block_size=2**12, hash_func=hashlib.sha256
):
    """
    This will get the hash of a random subset of the file.

    This is done because hashing gigabytes of audio content can be time
    consuming, and it is very unlikely that any given audio file will have a
    hash collision for a large subset of its file.

    The reason this is done randomly is because a lot of MP3 files have large
    amounts of metadata at the beginning and/or end of the file, and blocks
    at the beginning and/or end of the file are much more likely to have hash
    collisions within a given audiobook/series, etc. Hopefully, a more or less
    uniform sample of the whole file is the best subsampling strategy.

    :param fpath:
        The path of the file that is to be hashed.

    :param hashseed:
        The seed that will be fed to random.seed() when generating the samples.

    :param hash_amt:
        The amount of the file to hash, in bytes - if the file is smaller than
        this, the full file will be hashed.  If not divisible by ``block_size``,
        this will be rounded up to the nearest multiple of ``block_size``.

    :param block_size:
        The size of hash blocks - the file will be divided into chunks of this
        size and a random subset of these chunks will be hashed.

    :param hash_func:
        The hash function to use. This is expected to implement the interface
        of a :module:`hashlib` hash. Defaults to :pyfunc:`hashlib.sha256`.

    :return:
        Returns a hex digest of the randomly-hashed subset.
    """
    hash_amt = int(block_size * math.ceil(hash_amt / block_size))

    file_size = os.path.getsize(fpath)
    num_blocks = int(math.ceil(file_size / block_size))
    range_sample = range(0, num_blocks)
    if file_size < hash_amt:
        file_sample = range_sample
    else:
        num_used_blocks = hash_amt // block_size
        random.seed(hashseed)
        file_sample = sorted(random.sample(range_sample, num_used_blocks))

    hash_obj = hash_func()
    with open(fpath, "rb") as f:
        for ii in file_sample:
            f.seek(ii * block_size)
            hash_obj.update(f.read(block_size))

    return hash_obj.hexdigest()


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
        feed_item["guid"] = hash_random(audio_file, entry_obj.hashseed)

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
        return "<![CDATA[" + field + "]]>"
    else:
        # If there's already escaped data like &amp;, I want to unescape it
        # first, so I can re-escape *everything*
        field = saxutils.unescape(field)

        return saxutils.escape(field)


def _urljoin_dir(dir_, fragment):
    if not dir_.endswith("/"):
        dir_ += "/"

    return urljoin(dir_, fragment)


class ItemNotFoundError(ValueError):
    pass
