"""Utilities for determining information about the files."""

import copy
import datetime
import functools
import io
import itertools
import json
import logging
import operator
import os
import pathlib
import re
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import (
    Callable,
    Iterable,
    Mapping,
    MutableSequence,
    Sequence,
)
from typing import Any, Self, TypedDict, cast

import attrs

_SECOND = datetime.timedelta(seconds=1)


def _parse_time(s: str) -> float:
    components = ("seconds", "minutes", "hours")
    s_comps = s.split(":")
    if len(s_comps) > 3:
        raise ValueError(f"Unknown time format: {s}")

    kwargs = {}
    for comp_name, comp in zip(components, reversed(s_comps)):
        kwargs[comp_name] = float(comp)

    return datetime.timedelta(**kwargs) / _SECOND


# There are other keys in these results, but we aren't using them yet.
class JSONChapterType(TypedDict, total=False):
    id: int
    start_time: str
    end_time: str
    tags: Mapping[str, str]


class JSONFormatType(TypedDict, total=False):
    filename: str
    format_name: str
    format_long_name: str
    start_time: str
    duration: str
    size: str
    bit_rate: str
    tags: Mapping[str, str]


class FFProbeReturnJSON(TypedDict, total=False):
    chapters: Sequence[JSONChapterType]
    format: JSONFormatType


@attrs.frozen(order=True)
class OverdriveMediaMarker:
    time: float
    name: str | None = attrs.field(default=None, order=False)

    @classmethod
    def from_xml(cls, xml: str) -> Sequence[Self]:
        root = ET.fromstring(xml)
        if root.tag != "Markers":
            raise ValueError(
                f"Unknown media marker tag: {root.tag}. " + "Should be 'Markers'"
            )

        out: MutableSequence[Self] = []
        for marker_element in root:
            name_tag = marker_element.find("Name")
            name = name_tag.text if name_tag is not None else None

            time_tag = marker_element.find("Time")
            if time_tag is None or time_tag.text is None:
                raise ValueError("Media marker is missing a time")

            out.append(cls(time=_parse_time(time_tag.text), name=name))

        return out


def _filter_sparse(_: attrs.Attribute, value: Any) -> bool:
    return value is not None


# TODO: Switch to using attrs.AttrsInstance after attrs > 22.1 is released.
def _to_dict_sparse(attrs_instance: Any) -> Mapping[str, Any]:
    return attrs.asdict(attrs_instance, filter=_filter_sparse)


@attrs.define
class ChapterInfo:
    num: int
    start_time: float
    end_time: float
    title: str | None = None
    tags: Mapping[str, str] = attrs.field(factory=dict)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def to_json(self) -> JSONChapterType:
        out: JSONChapterType = {
            "id": self.num,
            "start_time": f"{self.start_time:0.4f}",
            "end_time": f"{self.end_time:0.4f}",
        }

        if self.tags:
            out["tags"] = copy.deepcopy(self.tags)

        return out

    @classmethod
    def from_json(cls, chapter: JSONChapterType) -> Self:
        if "tags" in chapter:
            tags: Mapping[str, str] = chapter["tags"]
        else:
            tags = {}

        title = tags.get("title", None)
        if title is not None:
            tags = {tag: value for tag, value in tags.items() if tag != "title"}

        start_time, end_time = (
            float(chapter[label]) for label in ("start_time", "end_time")  # type: ignore[literal-required]
        )
        num = int(chapter["id"])

        return cls(num, start_time, end_time, title=title, tags=tags)


@attrs.frozen
class FormatInfo:
    filename: str | None = attrs.field(default=None)
    format_name: str | None = attrs.field(default=None)
    format_long_name: str | None = attrs.field(default=None)
    start_time: float | None = attrs.field(default=None)
    duration: float | None = attrs.field(default=None)
    size: int | None = attrs.field(default=None)  # Bytes
    bit_rate: int | None = attrs.field(default=None)
    tags: Mapping[str, str] = attrs.field(factory=dict)

    def to_json(self) -> JSONFormatType:
        return cast(JSONFormatType, _to_dict_sparse(self))

    @classmethod
    def from_json(cls, json_dict: JSONFormatType) -> Self:
        def identity(x: str) -> str:
            return x

        component_conversion: Mapping[str, Callable[[str], Any]] = {
            "filename": identity,
            "format_name": identity,
            "format_long_name": identity,
            "start_time": float,
            "duration": float,
            "bit_rate": int,
            "size": int,
            "tags": identity,
        }

        kwargs: dict[str, Any] = {}
        for comp, converter in component_conversion.items():
            if comp in json_dict:
                kwargs[comp] = converter(json_dict[comp])  # type: ignore[literal-required]

        return cls(**kwargs)


@attrs.frozen
class FileInfo:
    format_info: FormatInfo
    chapters: Sequence[ChapterInfo] | None = attrs.field(default=None)

    @classmethod
    def from_json(cls, json_dict: FFProbeReturnJSON) -> Self:
        format_info = FormatInfo.from_json(json_dict["format"])

        chapters = []
        if json_dict["chapters"]:
            for chapter in json_dict["chapters"]:
                chapters.append(ChapterInfo.from_json(chapter))
        else:
            omm_tag = "OverDrive MediaMarkers"
            if omm_tag in format_info.tags:
                omm_tags = OverdriveMediaMarker.from_xml(format_info.tags[omm_tag])
                omm_tags = sorted(omm_tags)
                assert format_info.duration is not None  # TODO: Handle this gracefully

                for num, start_tag, end_tag in zip(
                    itertools.count(1),
                    omm_tags,
                    itertools.chain(
                        omm_tags[1:], (OverdriveMediaMarker(time=format_info.duration),)
                    ),
                ):
                    chapters.append(
                        ChapterInfo(
                            num=num,
                            start_time=start_tag.time,
                            end_time=end_tag.time,
                            title=start_tag.name,
                        )
                    )

        return cls(format_info=format_info, chapters=chapters)

    def to_json(self) -> FFProbeReturnJSON:
        rv: FFProbeReturnJSON = {
            "format": self.format_info.to_json(),
        }

        if self.chapters is not None:
            rv["chapters"] = tuple(map(operator.methodcaller("to_json"), self.chapters))

        return rv

    @classmethod
    def from_file(cls, fpath: pathlib.Path) -> Self:
        return cls.from_json(_read_file_info(fpath))

    _FFMETADATA_SPECIALS = re.compile(r"([\\#;=\n])")

    def to_ffmetadata(self) -> str:
        """Writes the file info in the FFMETADATA format."""

        escape_str = functools.partial(self._FFMETADATA_SPECIALS.sub, r"\\\g<1>")

        out = io.StringIO(";FFMETADATA1\n")
        out.seek(0, 2)  # Go to end of stream

        for tag, value in self.format_info.tags.items():
            out.write(f"{escape_str(tag)}={escape_str(value)}\n")

        chapters = self.chapters
        if chapters:
            for chapter_info in chapters:
                # TIMEBASE=1/1000 ⇒ chapter times are integers in units of ms
                out.write(
                    "[CHAPTER]\n"
                    + "TIMEBASE=1/1000\n"
                    + f"START={int(chapter_info.start_time * 1000)}\n"
                    + f"END={int(chapter_info.end_time * 1000)}\n"
                )
                if chapter_info.title is not None:
                    out.write(f"TITLE={escape_str(chapter_info.title)}\n")

                for tag, value in chapter_info.tags.items():
                    if tag != "title":
                        out.write(f"{escape_str(tag)}={escape_str(value)}\n")

        out.seek(0)
        return out.read()


def _read_file_info(fpath: pathlib.Path) -> FFProbeReturnJSON:
    proc = subprocess.run(
        [
            "ffprobe",
            "-i",
            os.fspath(fpath),
            "-print_format",
            "json",
            "-show_chapters",
            "-show_format",
            "-v",
            "quiet",
            "-loglevel",
            "error",
        ],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )

    if proc.stderr:  # pragma: nocover
        logging.error("Error in file %s: %s", fpath, proc.stderr)

    ffprobe_info = json.loads(proc.stdout)

    return ffprobe_info


def get_multipath_chapter_info(
    fpaths: Iterable[pathlib.Path],
    /,
    fall_back_to_durations: bool = False,
    file_infos: Mapping[pathlib.Path, FileInfo] | None = None,
) -> Sequence[tuple[pathlib.Path, ChapterInfo]]:
    out: MutableSequence[tuple[pathlib.Path, ChapterInfo]] = []
    chapter_num: int | None = None
    if file_infos is None:
        file_infos = {}

    for fpath in fpaths:
        if fpath in file_infos:
            file_info = file_infos[fpath]
        else:
            file_info = FileInfo.from_file(fpath)

        format_info = file_info.format_info
        if file_info.chapters and not any(
            (format_info.duration is not None) and (c.start_time) > format_info.duration
            for c in file_info.chapters
        ):  # If a chapter starts after the file ends, the metadata is bad
            for chapter in file_info.chapters:
                if chapter_num is None:
                    chapter_num = chapter.num
                else:
                    chapter_num += 1

                out.append((fpath, attrs.evolve(chapter, num=chapter_num)))
        elif fall_back_to_durations:
            if chapter_num is None:
                chapter_num = 1
            else:
                chapter_num += 1

            title = format_info.tags.get("title", "")
            if not title:
                title = fpath.name
                if not title[-1].isdecimal() and "track" in format_info.tags:
                    title += " " + format_info.tags["track"]

            duration = format_info.duration
            if duration is None:  # pragma: nocover
                raise ValueError(f"No duration information found for {fpath}")

            out.append(
                (
                    fpath,
                    ChapterInfo(
                        num=chapter_num,
                        start_time=0,
                        end_time=duration,
                        title=title,
                        tags=format_info.tags,
                    ),
                )
            )

    return out


def get_file_duration(fpath: pathlib.Path) -> datetime.timedelta | None:
    p = subprocess.run(
        [
            "ffprobe",
            "-i",
            os.fspath(fpath),
            "-show_entries",
            "format=duration",
            "-loglevel",
            "error",
            "-of",
            "csv=p=0",
        ],
        capture_output=True,
    )
    if p.returncode:
        logging.warning(
            "Failed to get duration for %s, error:\n%s",
            os.fspath(fpath),
            p.stderr.decode("utf-8").strip(),
        )
        return None

    return datetime.timedelta(seconds=float(p.stdout.decode("utf-8").strip()))
