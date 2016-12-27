"""
RSS Feed generators
"""
from datetime import timedelta
import hashlib
import math
import os
import random

from .config import read_from_config
from . import directory_parser as dp
from . import database_handler as dh

def hash_random(fpath, hashseed, hash_amt=2**20, block_size=2**12,
                hash_func=hashlib.sha256):
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
    with open(fpath, 'rb') as f:
        for ii in file_sample:
            f.seek(ii * block_size)
            hash_obj.update(f.read(block_size))

    return hash_obj.hexdigest()


def load_feed_items(entry_obj, loader=dp.AudiobookLoader):
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
    base_path = read_from_config('static_media_path')

    audio_dir = os.path.join(base_path, entry_obj.path)
    if not os.path.exists(audio_dir):
        raise ItemNotFoundError('Could not find item: {}'.format(audio_dir))

    pub_date = entry_obj.date_added
    data_obj = dh.get_database_table(entry_obj.table)[entry_obj.data_id]

    audio_files = loader.audio_files(audio_dir)

    feed_items = []
    for ii, audio_file in enumerate(audio_files):
        feed_item = {}

        relpath = os.path.relpath(audio_file, base_path)

        file_size =  os.path.getsize(audio_file)
        feed_item['size'] = file_size
        feed_item['url'] = relpath
        feed_item['pubdate'] = pub_date + timedelta(minutes=ii)
        feed_item['desc'] = data_obj.description or ''
        feed_item['guid'] = hash_random(audio_file, entry_obj.hashseed)

        feed_items.append(feed_item)

    return feed_items


class ItemNotFoundError(ValueError):
    pass

