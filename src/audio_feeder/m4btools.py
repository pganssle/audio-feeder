"""Tools to split or create chaptered m4b files."""
import copy
import functools
import io
import logging
import math
import operator
import os
import shutil
import subprocess
import tempfile
import typing
from concurrent import futures
from pathlib import Path
from typing import (
    Any,
    Callable,
    Iterable,
    Mapping,
    MutableMapping,
    MutableSequence,
    Optional,
    Sequence,
    Tuple,
    TypedDict,
    Union,
)

import attrs
import lxml

from . import directory_parser as dp
from . import file_probe, segmenter
from .file_probe import ChapterInfo


@attrs.frozen(order=True)
class SegmentableFiles:
    fpath: Path
    duration: float
    chapter: file_probe.ChapterInfo
    file_info: file_probe.FileInfo

    def __float__(self):
        return self.duration


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


@typing.overload
def _to_file_list_entry(p: Path, s: None, e: None) -> str:  # pragma: nocover
    ...


@typing.overload
def _to_file_list_entry(p: Path, s: float, e: float) -> str:  # pragma: nocover
    ...


def _to_file_list_entry(p, s=None, e=None):
    if s is None:
        pathstr = os.fspath(p)
        pathstr = pathstr.replace("'", r"\'")
        return f"file '{pathstr}'"
    else:
        return (
            f"{_to_file_list_entry(p)}\n"
            + f"inpoint {s:0.3f}\n"
            + f"outpoint {e:0.3f}\n"
            + f"duration {e-s:0.3f}\n"
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
    with tempfile.TemporaryDirectory() as td:
        tp = Path(td)

        file_list = tp / "input_files.txt"
        file_list.write_text("\n".join(map(_to_file_list_entry, files)))  # type: ignore[arg-type]
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


def _get_chapter_zero_padding(chap_info: Iterable[ChapterInfo]) -> int:
    max_chap = max(map(operator.attrgetter("num"), chap_info))
    return int(math.ceil(math.log(max_chap + 1, 10)))


def _merge_subsets(
    in_paths: Sequence[Tuple[Path, float, float]],
    out_path: Path,
    file_info: file_probe.FileInfo,
) -> None:
    with tempfile.TemporaryDirectory() as td:
        tp = Path(td)
        file_list = tp / "input_files.txt"
        file_list.write_text(
            "\n".join(_to_file_list_entry(p, s, e) for p, s, e in in_paths)
        )

        cmd = [
            "ffmpeg",
            "-loglevel",
            "error",
            "-i",
            "pipe:",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            os.fspath(file_list),
            "-map_metadata",
            "1",
            "-map_metadata",
            "0",
            "-c",
            "copy",
            os.fspath(out_path),
        ]

        proc = subprocess.run(
            cmd,
            input=file_info.to_ffmetadata(),
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

        if proc.stdout:  # pragma: nocover
            logging.info(proc.stdout)

        if proc.stderr:  # pragma: nocover
            logging.error(proc.stderr)

        if proc.returncode != 0:
            raise IOError(f"ffmpeg failed with exit code: {proc.returncode}")


def _extract_subset(
    in_path: Path,
    out_path: Path,
    file_info: file_probe.FileInfo,
) -> None:
    assert file_info.chapters
    if len(file_info.chapters) == 1:
        chapter = file_info.chapters[0]
    else:
        chapter = attrs.evolve(
            file_info.chapters[0], end_time=file_info.chapters[-1].end_time
        )
    logging.info("Extracting chapter %s from %s", chapter.num, in_path)

    new_tags: typing.MutableMapping[str, str] = typing.cast(
        typing.MutableMapping[str, str], copy.copy(file_info.format_info.tags)
    )
    if "title" not in new_tags:
        new_tags["title"] = chapter.title or ""
    if "track" not in new_tags:
        new_tags["track"] = str(chapter.num)

    file_info = attrs.evolve(
        file_info, format_info=attrs.evolve(file_info.format_info, tags=new_tags)
    )

    if chapter.start_time >= chapter.end_time:
        logging.warning(
            "Skipping malformed chapter with zero or negative length: "
            + "Chapter %s (%s has start time %s and end time %s",
            chapter.num,
            chapter.title,
            chapter.start_time,
            chapter.end_time,
        )
        return

    cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-i",
        "pipe:",
        "-ss",
        str(chapter.start_time),
        "-to",
        str(chapter.end_time),
        "-i",
        os.fspath(in_path),
        "-map_metadata",
        "1",
        "-map_metadata",
        "0",
        "-c",
        "copy",
        os.fspath(out_path),
    ]

    logging.debug("Executing ffmpeg command: %s", cmd)

    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        encoding="utf-8",
        input=file_info.to_ffmetadata(),
    )

    if proc.stdout:  # pragma: nocover
        logging.info(proc.stdout)

    if proc.stderr:  # pragma: nocover
        logging.error(proc.stderr)

    if proc.returncode != 0:
        raise IOError(f"ffmpeg failed with exit code: {proc.returncode}")


def split_chapters(
    in_path: Path,
    out_dir: Path,
    base_name: Optional[str] = None,
    *,
    audio_loader: dp.BaseAudioLoader = dp.AudiobookLoader(),
    executor: Optional[futures.Executor] = None,
) -> None:
    if in_path.is_dir():
        files = audio_loader.audio_files(in_path)
        ext = files[0].suffix
    else:
        files = [in_path]
        ext = in_path.suffix

    file_infos = {file: file_probe.FileInfo.from_file(file) for file in files}

    chapter_info = file_probe.get_multipath_chapter_info(
        files, file_infos=file_infos, fall_back_to_durations=False
    )

    if not out_dir.exists():
        out_dir.mkdir()

    zero_padding = _get_chapter_zero_padding(map(operator.itemgetter(1), chapter_info))

    if base_name is None:
        base_name = in_path.stem

    chap_num_fmt_str = f"{{:0{zero_padding}d}}"

    JobPoolJob = Tuple[
        Callable,
        Union[Path, Sequence[Tuple[Path, float, float]]],
        Path,
        file_probe.FileInfo,
    ]
    job_pool: MutableSequence[JobPoolJob] = []
    last_file: Optional[Path] = None
    for fpath, chapter in chapter_info:
        chap_num = chap_num_fmt_str.format(chapter.num)
        fname = f"{base_name} - {chap_num}{ext}"
        out_path = out_dir / fname

        if last_file != fpath and chapter.start_time > 0 and job_pool:
            old_job = job_pool.pop()
            (old_chapter,) = old_job[3].chapters  # type: ignore[misc]

            new_job: JobPoolJob = (
                _merge_subsets,
                [
                    (old_job[1], old_chapter.start_time, old_chapter.end_time),  # type: ignore[list-item]
                    (fpath, 0.0, chapter.start_time),
                ],
                old_job[2],
                attrs.evolve(
                    old_job[3],
                    chapters=[
                        attrs.evolve(
                            old_chapter,
                            end_time=old_chapter.end_time + chapter.start_time,
                        )
                    ],
                ),
            )
            job_pool.append(new_job)

        # Create a new FileInfo for the new file
        file_info = file_probe.FileInfo(
            format_info=attrs.evolve(
                file_infos[fpath].format_info,
                filename=fname,
                duration=chapter.duration,
                size=None,
            ),
            chapters=[attrs.evolve(chapter, start_time=0.0, end_time=chapter.duration)],
        )

        job_pool.append((_extract_subset, fpath, out_path, file_info))
        last_file = fpath

    if executor is None:
        executor = futures.ThreadPoolExecutor()

    def execute_job(job: JobPoolJob) -> None:
        f, *args = job
        f(*args)

    list(executor.map(execute_job, job_pool))


def segment_files(
    in_path: Path,
    out_path: Path,
    *,
    copy_on_optimal: bool = False,
    audio_loader: dp.BaseAudioLoader = dp.AudiobookLoader(),
    cost_func: Optional[segmenter.CostFunc] = None,
    executor: Optional[futures.Executor] = None,
) -> bool:

    if in_path.is_dir():
        files = audio_loader.audio_files(in_path)
    else:
        files = [in_path]

    file_infos = {fpath: file_probe.FileInfo.from_file(fpath) for fpath in files}

    chapter_infos = file_probe.get_multipath_chapter_info(
        files, fall_back_to_durations=True, file_infos=file_infos
    )

    segmentables = [
        SegmentableFiles(
            file,
            duration=chapter.duration,
            chapter=chapter,
            file_info=attrs.evolve(
                file_infos[file],
                format_info=attrs.evolve(
                    file_infos[file].format_info,
                    duration=chapter.duration,
                ),
                chapters=[
                    attrs.evolve(chapter, start_time=0.0, end_time=chapter.duration)
                ],
            ),
        )
        for file, chapter in chapter_infos
    ]

    if cost_func is None:
        kwargs = {}
    else:
        kwargs = {"cost_func": cost_func}

    segmented = segmenter.segment(segmentables, **kwargs)

    optimal = True
    job_queue: MutableSequence[Callable[[], Any]] = []
    zero_padding = int(math.ceil(math.log(len(segmented) + 1, 10)))
    padding_format = f"0{zero_padding:d}d"
    ext = files[0].suffix[1:]

    for i, segment in enumerate(segmented):
        out_file = out_path / f"Part{format(i, padding_format)}.{ext}"
        if len(segment) == 1:
            duration = segment[0].file_info.format_info.duration
            assert duration is not None
            if duration > segment[0].chapter.duration:
                optimal = False
                segment_file_info = segment[0].file_info

                job_queue.append(
                    functools.partial(
                        _extract_subset, segment[0].fpath, out_path, segment_file_info
                    )
                )

            else:
                job_queue.append(
                    functools.partial(shutil.copyfile, segment[0].fpath, out_file)
                )
        else:
            optimal = False
            # We have multiple segments merging into one. These could be subsets
            # of the same file or subsets of different files.
            segment_file_info = functools.reduce(
                _merge_file_infos, map(operator.attrgetter("file_info"), segment)
            )

            if all(segment[0].fpath == element.fpath for element in segment[1:]):
                # All from the same file, so we can use _extract_subset
                job_queue.append(
                    functools.partial(
                        _extract_subset, segment[0].fpath, out_file, segment_file_info
                    )
                )
            else:
                # We need to use _merge_subsets
                in_paths = [
                    (
                        element.fpath,
                        element.chapter.start_time,
                        element.chapter.end_time,
                    )
                    for element in segment
                ]
                job_queue.append(
                    functools.partial(
                        _merge_subsets, in_paths, out_file, segment_file_info
                    )
                )

    if optimal and not copy_on_optimal:
        return False

    if executor is None:
        executor = futures.ThreadPoolExecutor()

    list(executor.map(lambda x: x(), job_queue))

    return not optimal
