"""
RSS Feed generators
"""
import datetime
import functools
import json
import os
import re
import typing
from concurrent import futures
from datetime import timedelta
from urllib.parse import urljoin
from xml.sax import saxutils

from . import _object_types as ot
from . import database_handler as dh
from . import directory_parser as dp
from . import file_probe as fp
from . import object_handler as oh
from ._db_types import TableName
from .file_location import FileLocation
from .hash_utils import hash_random
from .resolver import Resolver

_T = typing.TypeVar("_T")


class _JSONChapter(typing.TypedDict, total=False):
    startTime: float
    endTime: float
    title: typing.Optional[str]


def _make_chapter_json(chapter: fp.ChapterInfo) -> _JSONChapter:
    out: _JSONChapter = {
        "startTime": chapter.start_time,
        "endTime": chapter.end_time,
    }

    if chapter.title is not None:
        out["title"] = chapter.title

    return out


def generate_chapter_json(chapter_infos: typing.Sequence[fp.ChapterInfo]) -> str:
    """Generate JSON files in the JSON Chapters format.

    For more details, see:
    https://github.com/Podcastindex-org/podcast-namespace/blob/4860bc5bf1ba9c200a3fac75354fa0dfe3c724e8/chapters/jsonChapters.md

    :param chapter_infos:
        A sequence of ChapterInfo objects, with start and end times relative
        to the specific media file.

    :returns:
        A string representing the chapters in JSON format.
    """

    return json.dumps(
        {"version": "1.2.0", "chapters": list(map(_make_chapter_json, chapter_infos))}
    )


def format_datetime(dt: datetime.datetime) -> str:
    # RFC 822 datetime
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")


def _get_description(data_obj: ot.SchemaObject, metadata: fp.FileInfo):
    chapter_descs = []
    if metadata.chapters:
        for chapter in metadata.chapters:
            if "description" in chapter.tags:
                chapter_desc = chapter.tags["description"]
            elif "comment" in chapter.tags:
                chapter_desc = chapter.tags["comment"]
            else:
                continue

            chapter_descs.append(f"Chapter {chapter.num}\n{chapter_desc}")

    if chapter_descs:
        return "\n".join(chapter_descs)

    if metadata.format_info.tags:
        if "description" in metadata.format_info.tags:
            return metadata.format_info.tags["description"]
        elif "comment" in metadata.format_info.tags:
            return metadata.format_info.tags["comment"]

    return getattr(data_obj, "description", None) or ""


def feed_items_from_metadata(
    entry_obj: oh.Entry,
    data_obj: ot.SchemaObject,
    audio_dir: FileLocation,
    file_metadata: typing.Mapping[
        FileLocation, typing.Tuple[fp.FileInfo, typing.Optional[str]]
    ],
    mode: typing.Optional[str] = None,
    resolver=None,
) -> typing.Sequence[typing.Mapping[str, typing.Any]]:
    pub_date = entry_obj.date_added or datetime.datetime.now(datetime.timezone.utc)

    feed_items: typing.MutableSequence[typing.Mapping[str, typing.Any]] = []
    for ii, (file, (file_info, file_hash)) in enumerate(file_metadata.items()):
        feed_item: typing.MutableMapping[str, typing.Any] = {}

        url = file.url
        fpath = file.path
        assert fpath
        file_size = file_info.format_info.size
        if not file_size and fpath.exists():
            file_size = os.path.getsize(fpath)

        if file_size:
            feed_item["size"] = file_size

        feed_item["fname"] = fpath.name
        feed_item["url"] = url
        feed_item["pubdate"] = format_datetime(pub_date + timedelta(minutes=ii))
        feed_item["desc"] = _get_description(data_obj, file_info)

        if file_hash is None:
            assert entry_obj.hashseed
            file_hash = hash_random(fpath, entry_obj.hashseed).hex()

        feed_item["guid"] = file_hash

        if file_info.chapters:
            chapters_url = resolver.resolve_chapter(
                entry_obj,
                file_hash,
            ).url
            if mode is not None:
                chapters_url += f"?mode={mode}"
            feed_item["chapters_url"] = chapters_url
        else:
            feed_item["chapters_url"] = None

        feed_items.append({k: wrap_field(v) for k, v in feed_item.items()})

    return feed_items


def load_feed_items(
    entry_obj: oh.Entry,
    resolver: typing.Optional[Resolver] = None,
    loader: dp.BaseAudioLoader = dp.AudiobookLoader(),
):
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

    media_path = resolver.resolve_media(".").path
    audio_dir = resolver.resolve_media(os.fspath(entry_obj.path))
    assert audio_dir.path is not None
    assert media_path is not None
    if not audio_dir.path.exists():
        raise ItemNotFoundError(f"Could not find item: {audio_dir}")

    table = entry_obj.table
    assert table is not None
    data_obj = dh.get_database_table(TableName(table))[entry_obj.data_id]

    audio_files = loader.audio_files(audio_dir.path)

    @functools.cache
    def _executor() -> futures.Executor:
        return futures.ThreadPoolExecutor()

    metadata_futures: typing.MutableSequence[
        futures.Future[typing.Tuple[FileLocation, fp.FileInfo, typing.Optional[str]]]
    ] = []
    file_metadata: typing.MutableMapping[
        FileLocation, typing.Tuple[fp.FileInfo, typing.Optional[str]]
    ] = {}
    for file in audio_files:
        fname = file.relative_to(audio_dir.path)

        file_loc = FileLocation(
            rel_path=fname, url_base=audio_dir.url, path_base=audio_dir.path
        )

        m_rel_path = file.relative_to(media_path)
        if entry_obj.file_hashes and m_rel_path in entry_obj.file_hashes:
            file_hash: typing.Optional[str] = entry_obj.file_hashes[m_rel_path]
        else:
            file_hash = None

        if entry_obj.file_metadata is None or m_rel_path not in entry_obj.file_metadata:
            metadata_futures.append(
                _executor().submit(
                    lambda fl, fh: (fl, fp.FileInfo.from_file(fl.path), fh),
                    file_loc,
                    file_hash,
                )
            )
        else:
            file_metadata[file_loc] = (entry_obj.file_metadata[m_rel_path], file_hash)

    for f in futures.as_completed(metadata_futures):
        file_loc, metadata, file_hash = f.result()
        file_metadata[file_loc] = (metadata, file_hash)

    return feed_items_from_metadata(
        entry_obj,
        data_obj,
        audio_dir,
        file_metadata={
            k: v for k, v in sorted(file_metadata.items(), key=lambda x: x[0].path)  # type: ignore
        },
        resolver=resolver,
    )


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
