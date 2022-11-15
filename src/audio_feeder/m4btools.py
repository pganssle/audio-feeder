"""Tools to split or create chaptered m4b files."""
import functools
import io
import logging
import math
import operator
import os
import subprocess
import tempfile
from concurrent import futures
from pathlib import Path
from typing import (
    Any,
    Mapping,
    MutableMapping,
    MutableSequence,
    Optional,
    Sequence,
    TypedDict,
)

import attrs
import lxml

from . import directory_parser as dp
from . import file_probe
from .file_probe import ChapterInfo


def _merge_file_infos(
    f1: file_probe.FileInfo, f2: file_probe.FileInfo, /
) -> file_probe.FileInfo:
    fi1 = f1.format_info
    fi2 = f2.format_info
    if fi1.duration is None or fi2.duration is None:  # pragma: nocover
        raise ValueError(f"Cannot merge file info without file durations.")

    new_format_info: MutableMapping[str, Any] = {
        "start_time": fi1.start_time,
        "duration": fi1.duration + fi2.duration,
        "size": None,
        "bit_rate": fi1.bit_rate if fi1.bit_rate == fi2.bit_rate else None,
        "tags": {},
    }

    new_format_info["tags"].update(fi2.tags)
    new_format_info["tags"].update(fi1.tags)

    new_chapters = list(f1.chapters or ())
    if f2.chapters:
        if new_chapters and f2.chapters[0].start_time > 0.0:
            new_chapters[-1] = attrs.evolve(
                new_chapters[-1],
                end_time=new_chapters[-1].end_time + f2.chapters[0].start_time,
            )

        left_duration = fi1.duration
        for chapter in f2.chapters:
            new_chapters.append(
                attrs.evolve(
                    chapter,
                    start_time=chapter.start_time + left_duration,
                    end_time=chapter.end_time + left_duration,
                )
            )

    return file_probe.FileInfo(
        format_info=file_probe.FormatInfo(**new_format_info), chapters=new_chapters
    )


def make_single_file_chaptered(
    audio_dir: Path,
    out_path: Path,
    *,
    audio_loader: dp.BaseAudioLoader = dp.AudiobookLoader(),
    chapter_info: Optional[Mapping[Path, Sequence[ChapterInfo]]] = None,
) -> None:
    files = audio_loader.audio_files(audio_dir)
    if chapter_info is not None:
        if set(files) - chapter_info.keys():
            logging.warn(
                "Mismatch between pre-calculated chapter info files "
                + "and files on disk. Got:\n%s\nExpected:\n%s\n"
                + "Recalculating based on files on disk.",
                set(map(os.fspath, chapter_info.keys())),  # type: ignore[arg-type]
                set(map(os.fspath, files)),  # type: ignore[arg-type]
            )

            chapter_info = None

    file_infos = {fpath: file_probe.FileInfo.from_file(fpath) for fpath in files}

    # TODO: Refactor this so that we can directly invoke the "fall back to durations"
    # logic if necessary.
    for path in files:
        if file_infos[path].chapters:
            break
    else:
        if chapter_info is None:
            chapter_info_: MutableMapping[
                Path, MutableSequence[file_probe.ChapterInfo]
            ] = {}
            for path, chapter in file_probe.get_multipath_chapter_info(
                files, fall_back_to_durations=True, file_infos=file_infos
            ):
                chapter_info_.setdefault(path, []).append(chapter)
            chapter_info = chapter_info_
            del chapter_info_

        for path in files:
            file_infos[path] = attrs.evolve(
                file_infos[path], chapters=chapter_info[path]
            )

    # Create a new FileInfo object for our new m4b
    merged_file_info: file_probe.FileInfo = functools.reduce(
        _merge_file_infos, file_infos.values()
    )

    # Write the file info metadata to a temporary directory, then do the merge
    def _to_file_list_entry(p: Path) -> str:
        pathstr = os.fspath(p)
        pathstr = pathstr.replace("'", r"\'")
        return f"file '{pathstr}'"

    with tempfile.TemporaryDirectory() as td:
        tp = Path(td)

        file_list = tp / "input_files.txt"
        file_list.write_text("\n".join(map(_to_file_list_entry, files)))
        cmd = [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            os.fspath(file_list),
            "-i",
            "pipe:",
            "-map",
            "0",
            "-map_metadata",
            "1",
            "-c:a",
            "aac",
            "-c:v",
            "copy",
            "-q:a",
            "3",
            "-f",
            "mp4",
            os.fspath(out_path),
        ]
        logging.debug("Executing merge command:\n%s", cmd)
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            input=merged_file_info.to_ffmetadata(),
            encoding="utf-8",
        )

        if proc.stdout:  # pragma: nocover
            logging.info(proc.stdout)

        if proc.stderr:
            logging.error(proc.stderr)

        if proc.returncode:
            raise IOError(f"ffmpeg returned non-zero exit status: {proc.returncode}")
