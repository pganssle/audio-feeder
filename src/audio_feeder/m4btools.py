"""Tools to split or create chaptered m4b files."""
import copy
import functools
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
    Mapping,
    MutableMapping,
    MutableSequence,
    Optional,
    Sequence,
)

import attrs

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


@attrs.frozen
class FileSubset:
    path: Path
    start: Optional[float] = None
    end: Optional[float] = None


@attrs.frozen
class RenderJob:
    subsets: Sequence[FileSubset]
    out_path: Path
    out_file_info: file_probe.FileInfo

    def is_copy_job(self):
        if len(self.subsets) != 1:
            return False

        file_subset = self.subsets[0]
        return (
            file_subset.start is None or file_subset.start == 0.0
        ) and file_subset.end is None

    def __call__(self) -> None:
        if self.is_copy_job():
            shutil.copyfile(self.subsets[0].path, self.out_path)
            return
        elif all(self.subsets[0].path == fs.path for fs in self.subsets[1:]):
            # These are all subsets of a single file, so we can use _extract_subset
            # This also matches when there is exactly one file subset.
            if len(self.subsets) > 1:
                merged_subset = attrs.evolve(self.subsets[0], end=self.subsets[-1].end)
            else:
                merged_subset = self.subsets[0]

            _extract_subset(merged_subset, self.out_path, self.out_file_info)
            return
        else:
            # Multiple files merging into one, so we use _merge_subsets
            _merge_subsets(self.subsets, self.out_path, self.out_file_info)
            return


def _merge_file_infos(
    f1: file_probe.FileInfo, f2: file_probe.FileInfo, /
) -> file_probe.FileInfo:
    fi1 = f1.format_info
    fi2 = f2.format_info
    if fi1.duration is None or fi2.duration is None:  # pragma: nocover
        raise ValueError("Cannot merge file info without file durations.")

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


def _to_file_list_entry(p: Path, s: Optional[float] = None, e: Optional[float] = None):
    pathstr = os.fspath(p)
    pathstr = pathstr.replace("'", r"\'")
    o = f"file '{pathstr}'\n"
    if s is not None:
        o += f"inpoint {s:0.3f}\n"
    if e is not None:
        o += f"outpoint {e:0.3f}\n"
        if s is None:
            s = 0.0
        o += f"duration {e-s:0.3f}\n"
    return o


def single_file_chaptered_jobs(
    files: Sequence[Path],
    out_path: Path,
    *,
    chapter_info: Optional[Mapping[Path, Sequence[ChapterInfo]]] = None,
) -> Sequence[RenderJob]:
    if chapter_info is not None:
        if set(files) - chapter_info.keys():
            logging.warning(
                "Mismatch between pre-calculated chapter info files "
                + "and files on disk. Got:\n%s\nExpected:\n%s\n"
                + "Recalculating based on files on disk.",
                set(map(os.fspath, chapter_info.keys())),  # type: ignore[arg-type]
                set(map(os.fspath, files)),  # type: ignore[arg-type]
            )

            chapter_info = None

    file_infos = {fpath: file_probe.FileInfo.from_file(fpath) for fpath in files}
    subsets = [FileSubset(path=fpath, start=None, end=None) for fpath in files]

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

    return (
        RenderJob(subsets=subsets, out_path=out_path, out_file_info=merged_file_info),
    )


def _zero_padding_format(max_num: int) -> str:
    zero_padding = int(math.ceil(math.log(max_num + 1, 10)))
    return f"0{zero_padding:d}d"


def _merge_subsets(
    subsets: Sequence[FileSubset],
    out_path: Path,
    file_info: file_probe.FileInfo,
) -> None:
    if out_path.suffix.endswith("m4b") and any(
        not x.path.suffix.endswith("m4b") for x in subsets
    ):
        audio_codec = "aac"
    else:
        audio_codec = "copy"

    with tempfile.TemporaryDirectory() as td:
        tp = Path(td)
        file_list = tp / "input_files.txt"
        file_list.write_text(
            "\n".join(_to_file_list_entry(x.path, x.start, x.end) for x in subsets)
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
            "-c:a",
            audio_codec,
            "-c:v",
            "copy",
            os.fspath(out_path),
        ]

        logging.debug("Running ffmpeg command: %s", cmd)
        logging.debug("file list:\n%s", file_list.read_text())

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
    subset: FileSubset,
    out_path: Path,
    file_info: file_probe.FileInfo,
) -> None:
    assert file_info.chapters
    chapter = file_info.chapters[0]
    in_path = subset.path

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

    subset_directives: MutableSequence[str] = []
    if subset.start:
        subset_directives.extend(("-ss", str(subset.start)))

    if subset.end:
        subset_directives.extend(("-to", str(subset.end)))

    cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-i",
        "pipe:",
        *subset_directives,
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


def chapter_split_jobs(
    files: Sequence[Path],
    out_path: Path,
    base_name: Optional[str] = None,
) -> Sequence[RenderJob]:
    ext = files[0].suffix

    if base_name is None:
        base_name = "Chapter"

    file_infos = {file: file_probe.FileInfo.from_file(file) for file in files}

    chapter_info = file_probe.get_multipath_chapter_info(
        files, file_infos=file_infos, fall_back_to_durations=False
    )

    max_chapter = max(chapter.num for _, chapter in chapter_info)
    padding_format = _zero_padding_format(max_chapter)

    job_pool: MutableSequence[RenderJob] = []
    last_file: Optional[Path] = None
    for fpath, chapter in chapter_info:
        out_file = out_path / f"{base_name}{format(chapter.num, padding_format)}{ext}"
        logging.debug("Adding job to generate %s", out_file)

        if last_file != fpath and chapter.start_time > 0 and job_pool:
            # We need to append the beginning of the next file into the end
            # of the last file, because the chapter is split across multiple
            # files.
            old_job: RenderJob = job_pool.pop()
            new_subsets = [
                *old_job.subsets,
                FileSubset(fpath, start=None, end=chapter.start_time),
            ]

            old_file_info = old_job.out_file_info
            assert old_file_info.chapters
            old_chapter = old_file_info.chapters[0]
            new_file_info = attrs.evolve(
                old_file_info,
                chapters=[
                    attrs.evolve(
                        old_chapter, end_time=old_chapter.end_time + chapter.start_time
                    )
                ],
            )
            new_job = RenderJob(
                subsets=new_subsets,
                out_path=old_job.out_path,
                out_file_info=new_file_info,
            )

            job_pool.append(new_job)

        if abs(chapter.end_time - file_infos[fpath].format_info.duration) < 0.25:
            end_time = None
        else:
            end_time = chapter.end_time

        file_subset = FileSubset(
            path=fpath,
            start=chapter.start_time,
            end=end_time,
        )

        # Create a new FileInfo for the new file
        file_info = file_probe.FileInfo(
            format_info=attrs.evolve(
                file_infos[fpath].format_info,
                duration=chapter.duration,
                size=None,
            ),
            chapters=[attrs.evolve(chapter, start_time=0.0, end_time=chapter.duration)],
        )

        job_pool.append(
            RenderJob(subsets=[file_subset], out_path=out_file, out_file_info=file_info)
        )
        last_file = fpath

    return job_pool


def segment_files_jobs(
    files: Sequence[Path],
    out_path: Path,
    *,
    cost_func: Optional[segmenter.CostFunc] = None,
) -> typing.Sequence[RenderJob]:
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

    job_queue: MutableSequence[RenderJob] = []
    padding_format = _zero_padding_format(len(segmented))

    ext = files[0].suffix
    for i, segment in enumerate(segmented):
        out_file = out_path / f"Part{format(i, padding_format)}{ext}"
        if len(segment) == 1:
            duration = segment[0].file_info.format_info.duration
            assert duration is not None
            chapter = segment[0].chapter
            if duration > chapter.duration:
                subset = FileSubset(
                    segment[0].fpath, start=chapter.start_time, end=chapter.end_time
                )
            else:
                subset = FileSubset(segment[0].fpath, start=chapter.start_time)
            job_queue.append(
                RenderJob(
                    [subset], out_path=out_file, out_file_info=segment[0].file_info
                )
            )
        else:
            segment_file_info = functools.reduce(
                _merge_file_infos, map(operator.attrgetter("file_info"), segment)
            )

            subsets: MutableSequence[FileSubset] = []
            for element in segment:
                duration = element.file_info.format_info.duration
                assert duration is not None
                if abs(element.chapter.end_time - duration) < 0.25:
                    end_time = None
                else:
                    end_time = element.chapter.end_time

                subsets.append(
                    FileSubset(
                        element.fpath, start=element.chapter.start_time, end=end_time
                    )
                )

            job_queue.append(
                RenderJob(subsets, out_path=out_file, out_file_info=segment_file_info)
            )

    return job_queue


def render_jobs(
    jobs: Sequence[RenderJob],
    *,
    executor: Optional[futures.Executor] = None,
) -> None:
    if executor is None:
        executor = futures.ThreadPoolExecutor()

    list(executor.map(lambda x: x(), jobs))
