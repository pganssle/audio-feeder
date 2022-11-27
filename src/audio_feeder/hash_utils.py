import hashlib
import math
import os
import pathlib
import random
import typing


class _Hash(typing.Protocol):
    def update(self, data: bytes) -> None:
        ...

    def hexdigest(self) -> str:
        ...

    def digest(self) -> bytes:
        ...


_HashFunc = typing.Callable[[], _Hash]


def hash_random(
    fpath: pathlib.Path,
    hashseed: int,
    hash_amt: int = 2**20,
    block_size: int = 2**12,
    hash_func: _HashFunc = hashlib.sha256,
) -> bytes:
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
    range_sample: typing.Sequence[int] = range(0, num_blocks)
    if file_size < hash_amt:
        file_sample = range_sample
    else:
        rng = random.Random(hashseed)
        num_used_blocks = hash_amt // block_size
        file_sample = sorted(rng.sample(range_sample, num_used_blocks))

    hash_obj = hash_func()
    with open(fpath, "rb") as f:
        for ii in file_sample:
            f.seek(ii * block_size)
            hash_obj.update(f.read(block_size))

    return hash_obj.digest()
