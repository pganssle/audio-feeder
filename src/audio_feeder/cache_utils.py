"""
Functions useful for caching.
"""


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
