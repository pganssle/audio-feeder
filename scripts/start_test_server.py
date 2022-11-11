import contextlib
import os
import pathlib
import shutil
import subprocess
import tempfile
import typing

import click

TEMP_DIR_NAME: typing.Final[str] = "audio_feeder_test_server"
TEMP_LOC: typing.Final[pathlib.Path] = (
    pathlib.Path(tempfile.gettempdir()) / TEMP_DIR_NAME
)

TEST_DATA_LOC: typing.Final[pathlib.Path] = (
    pathlib.Path(__file__).parent / "../tests/data"
)


@contextlib.contextmanager
def cwd(new_dir: pathlib.Path) -> typing.Iterator[None]:
    old_dir = pathlib.Path.cwd()
    try:
        os.chdir(new_dir)
        yield
    finally:
        os.chdir(old_dir)


def initialize(init_dir: pathlib.Path) -> None:
    if not init_dir.exists():
        init_dir.mkdir()
    elif any(init_dir.iterdir()):
        raise OSError(f"{init_dir} must either not exist or be an empty directory")

    subprocess.run(
        ["audio-feeder", "install", "--config-dir", os.fspath(init_dir)],
        cwd=init_dir,
        check=True,
    )

    shutil.copytree(TEST_DATA_LOC / "example_media", init_dir / "static/media")


def start_server(config_dir: pathlib.Path, profile: bool = False) -> None:
    cmd = ["audio-feeder", "run"]
    if profile:
        cmd.append("--profile")

    subprocess.run(cmd, cwd=config_dir, check=True)


@click.command()
@click.option(
    "--fresh-dir",
    is_flag=True,
    default=False,
    help="Delete existing working dir before running",
)
@click.option(
    "--config-dir",
    default=None,
    type=click.Path(
        path_type=pathlib.Path, exists=True, dir_okay=True, file_okay=False
    ),
    help="Use the specified directory instead of the default one.",
)
def main(fresh_dir: bool, config_dir: typing.Optional[pathlib.Path]) -> None:
    if fresh_dir and config_dir is not None:
        raise ValueError("Cannot specify both --config-dir and --fresh_dir")

    if config_dir is not None:
        base_dir = config_dir
    else:
        base_dir = TEMP_LOC

    if fresh_dir or not base_dir.exists() or not any(base_dir.iterdir()):
        if base_dir.exists():
            shutil.rmtree(base_dir)
        initialize(base_dir)

    start_server(base_dir)


if __name__ == "__main__":
    main()  # type: ignore
