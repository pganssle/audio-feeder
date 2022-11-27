"""Utilties for handling media rendering for derived feeds."""
import functools
import hashlib
import json
import logging
import os
import pathlib
import shutil
import threading
import typing
from concurrent import futures
from datetime import datetime, timezone

from . import _object_types as ot
from . import database_handler as dh
from . import directory_parser as dp
from . import file_probe as fp
from . import hash_utils, m4btools
from . import object_handler as oh
from ._compat import StrEnum
from ._db_types import TableName
from .resolver import get_resolver

ACTIVE_JOBS: typing.Set[pathlib.Path] = set()
JOB_LOCK: threading.Lock = threading.Lock()
RENDER_POOL: typing.Final[futures.Executor] = futures.ThreadPoolExecutor(
    thread_name_prefix="af-media-renderer"
)


class RenderModes(StrEnum):
    SINGLE_FILE = "SINGLEFILE"
    CHAPTERS = "CHAPTERS"
    SEGMENTED = "SEGMENTED"


class Renderer:
    def __init__(
        self,
        media_path: pathlib.Path,
        entry: oh.Entry,
        mode: RenderModes,
        *,
        loader: dp.BaseAudioLoader = dp.AudiobookLoader(),
        executor: typing.Optional[futures.Executor] = None,
    ):
        self.media_path: typing.Final[pathlib.Path] = media_path
        self.entry: typing.Final[oh.Entry] = entry
        self.mode: typing.Final[RenderModes] = mode
        self.data_obj: typing.Final[ot.SchemaObject] = self._get_data_obj()
        self._loader = loader
        self._executor = executor

    def _get_data_obj(self) -> ot.SchemaObject:
        if self.entry.table is None:
            raise ValueError(f"Invalid entry, must have table set: {self.entry}")
        data_table = dh.get_database_table(TableName(self.entry.table))

        if self.entry.data_id not in data_table:
            raise ValueError(f"Invalid data_id in entry: {self.entry.data_id}")

        return data_table[self.entry.data_id]

    @functools.cached_property
    def executor(self):
        if self._executor is None:
            return RENDER_POOL
        return self._executor

    @functools.cached_property
    def rss_file(self) -> pathlib.Path:
        return self.media_path / f"{self.entry.id}-{self.mode.lower()}.xml"

    def is_render_complete(self) -> bool:
        return (self.media_path / ".render_complete").exists()

    def is_default(self) -> bool:
        return (self.media_path / ".default").exists()

    def _mark_render_complete(self) -> None:
        self._touch_file(".render_complete")

    def _mark_as_default(self) -> None:
        self._touch_file(".default")

    def _touch_file(self, fname: str) -> None:
        (self.media_path / fname).touch()

    def render_complete_callback(
        self, rendering_futures: typing.Sequence[futures.Future]
    ) -> None:
        try:
            exception_found = False
            futures.wait(rendering_futures)
            for future in futures.as_completed(rendering_futures):
                if future.exception() is not None:
                    exception_found = True
                    logging.error("Rendering error: %s", future.exception())

            if not exception_found:
                if self.rss_file.exists():
                    # Delete the old RSS file, which needs to be refreshed
                    # after all the files have been generated.
                    self.rss_file.unlink()
                self._mark_render_complete()
        finally:
            with JOB_LOCK:
                ACTIVE_JOBS.remove(self.media_path)

    def trigger_rendering(self) -> None:
        if self.media_path in ACTIVE_JOBS or self.is_render_complete():
            return

        with JOB_LOCK:
            ACTIVE_JOBS.add(self.media_path)

        try:
            if not self.media_path.exists():
                self.media_path.mkdir()

            # Delete any left-over files from potential previous renderings
            for fpath in self.media_path.iterdir():
                if fpath.is_dir():
                    shutil.rmtree(fpath)
                else:
                    fpath.unlink()

            resolver = get_resolver()

            file_base = resolver.resolve_media(".").path
            assert file_base is not None

            if self.entry.files:
                files: typing.Sequence[pathlib.Path] = [
                    file_base / file for file in self.entry.files
                ]
            else:
                files = self._loader.audio_files(self.entry.path)

            if self.mode == RenderModes.SINGLE_FILE:
                jobs = m4btools.single_file_chaptered_jobs(files, self.media_path)
            elif self.mode == RenderModes.CHAPTERS:
                if (item_title := getattr(self.data_obj, "title", None)) is not None:
                    base_name = item_title + "-"
                else:
                    base_name = None

                jobs = m4btools.chapter_split_jobs(
                    files, self.media_path, base_name=base_name
                )
            elif self.mode == RenderModes.SEGMENTED:
                jobs = m4btools.segment_files_jobs(files, self.media_path)

            if all(x.is_copy_job() for x in jobs):
                self._mark_as_default()
                job_futures = []
            else:
                job_futures = [self.executor.submit(job) for job in jobs]

            # Spawn a background thread to wait on all the rendering jobs, then
            # mark the directory as having completed rendering. We are not using
            # the thread pool executor because we don't want to get into a deadlock
            # if the thread pool executor gets filled up with jobs waiting on actual
            # render jobs.
            threading.Thread(
                target=self.render_complete_callback, args=(job_futures,)
            ).start()

            assert self.entry.hashseed
            file_metadata = {
                job.out_path.relative_to(self.media_path): (
                    job.out_file_info,
                    self.make_hash(job),
                )
                for job in jobs
            }
            self.write_file_metadata(file_metadata)

        except:
            with JOB_LOCK:
                ACTIVE_JOBS.remove(self.media_path)
            raise

    def write_file_metadata(
        self,
        file_infos: typing.Mapping[pathlib.Path, typing.Tuple[fp.FileInfo, str]],
    ) -> None:
        json_obj = []
        for file_path, (file_info, file_hash) in file_infos.items():
            json_obj.append(
                {
                    "file_path": os.fspath(file_path),
                    "file_info": file_info.to_json(),
                    "file_hash": file_hash,
                }
            )

        with open(self.media_path / ".file_metadata", "wt") as f:
            json.dump(json_obj, f)

    def read_file_metadata(
        self,
    ) -> typing.Mapping[pathlib.Path, typing.Tuple[fp.FileInfo, str]]:
        with open(self.media_path / ".file_metadata", "rt") as f:
            json_obj = json.load(f)

        out = {}
        for data in json_obj:
            file_path = pathlib.Path(data["file_path"])
            file_info = fp.FileInfo.from_json(data["file_info"])
            file_hash = data["file_hash"]

            out[file_path] = (file_info, file_hash)

        return out

    def read_access_time(self) -> typing.Optional[datetime]:
        last_access_path = self.media_path / ".last_retrieved"
        if not last_access_path.exists():
            return None

        return datetime.fromisoformat(last_access_path.read_text())

    def update_access_time(self) -> None:
        (self.media_path / ".last_retrieved").write_text(
            datetime.now(timezone.utc).isoformat()
        )

    def make_hash(self, job: m4btools.RenderJob) -> str:
        # We cannot hash the file because we want to be able to generate the
        # RSS feed before the files are actually ready to download, but we can
        # work with the hashes of the input files.
        assert self.entry.hashseed is not None
        new_hash = hashlib.sha256()

        media_base = get_resolver().resolve_media(".").path
        assert media_base is not None
        old_hashes = []
        for subset in job.subsets:
            file = subset.path.relative_to(media_base)

            if self.entry.file_hashes and file in self.entry.file_hashes:
                old_hash = self.entry.file_hashes[file]
            else:
                old_hash = hash_utils.hash_random(
                    subset.path, self.entry.hashseed
                ).hex()

            old_hashes.append(
                (
                    old_hash,
                    job.out_path.relative_to(self.media_path),
                    job.out_file_info.format_info.duration or 0.0,
                )
            )

        for old_hash, out_path, new_duration in sorted(old_hashes):
            new_hash.update(old_hash.encode())
            new_hash.update(os.fspath(out_path).encode())
            new_hash.update(str(new_duration).encode())
        return new_hash.hexdigest()
