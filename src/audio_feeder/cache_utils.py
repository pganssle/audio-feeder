"""
Functions useful for caching.
"""
import functools
import typing

_FUNCTION_CACHES: typing.MutableMapping[str, typing.MutableSequence[typing.Any]] = {}

_T = typing.TypeVar("_T")


@functools.lru_cache(None)
def register_function_cache(cache_type: str) -> typing.Callable[[_T], _T]:
    def registration_decorator(f: _T) -> _T:
        _FUNCTION_CACHES.setdefault(cache_type, []).append(f)
        return f

    return registration_decorator


def clear_caches(cache_type: typing.Optional[str] = None) -> None:
    """Clears all caches of a given type.

    If cache_type is unspecified, all caches are cleared.
    """
    if cache_type is None:
        for ct in _FUNCTION_CACHES.keys():
            clear_caches(ct)
    else:
        for cache_func in _FUNCTION_CACHES.get(cache_type, ()):
            cache_func.cache_clear()


def populate_qr_cache(entry_table=None, resolver=None, pbar=lambda x: x):
    """
    Since generating the QR cache can be time-consuming during each page laod,
    this will opportunistically attempt to create the QR cache ahead of time.

    :param entry_table:
        The table of entries. If not specified, the global database will be
        used.

    :param resolver:
        The URL resolver (which actually creates the QR codes during url/path
        resolution). If not specified, global resolver is used.

    :param pbar:
        A :class:`progressbar2.ProgressBar`-style progress bar. By default, no
        progress is indicated.
    """
    if entry_table is None:
        from .database_handler import get_database_table

        entry_table = get_database_table("entries")

    if resolver is None:
        from .resolver import get_resolver

        resolver = get_resolver()

    for e_id, entry_obj in pbar(entry_table.items()):
        rss_url = resolver.resolve_rss(entry_obj)
        resolver.resolve_qr(e_id, rss_url.url)
