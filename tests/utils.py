import lzma
import os
import pathlib
import shutil
import subprocess
import typing

from audio_feeder import file_probe


def make_file(
    file_info: file_probe.FileInfo,
    out_path: pathlib.Path,
    freq: typing.Optional[int] = None,
) -> None:
    format_info = file_info.format_info
    duration = format_info.duration
    if freq is None:
        gen_filter = f"anullsrc=d={duration:0.3f}:r=44100:cl=mono"
    else:
        gen_filter = f"sine=f={freq}:d={duration:0.3f}:r=44100"

    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-i",
            "pipe:",
            "-f",
            "lavfi",
            "-i",
            gen_filter,
            "-q:a",
            "9",
            "-acodec",
            "libmp3lame",
            "-map_metadata",
            "0",
            "-map",
            "1",
            os.fspath(out_path),
        ],
        check=True,
        input=file_info.to_ffmetadata(),
        encoding="utf-8",
    )


def copy_with_unzip(src: pathlib.Path, dest: pathlib.Path):
    dest.mkdir(parents=True, exist_ok=True)
    for f in src.rglob("*"):
        rel_path = f.relative_to(src)
        dest_path = dest / rel_path
        if f.is_dir():
            dest_path.mkdir()
        elif f.suffix != ".xz":
            shutil.copy(f, dest_path)
        else:
            with lzma.open(f, "rb") as file_contents:
                dest_path.with_suffix("").write_bytes(file_contents.read())
