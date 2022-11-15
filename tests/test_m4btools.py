import itertools
import logging
import os
import pathlib
import subprocess
import tempfile
import typing
from concurrent import futures
from unittest import mock

import attrs
import pytest

from audio_feeder import file_probe, m4btools

from . import utils

DRACULA_DESC: typing.Final[
    str
] = """\
Dracula is an Gothic horror novel by Irish author Bram Stoker. Famous for
introducing the character of the vampire Count Dracula, the novel tells the
story of Dracula's attempt to move from Transylvania to England, and the battle
between Dracula and a small group of men and women led by Professor Abraham Van
Helsing.
"""

DRACULA_CHAPTERS: typing.Sequence[file_probe.ChapterInfo] = [
    file_probe.ChapterInfo(
        num=0,
        title="01 - Jonathan Harker's Journal",
        start_time=0.0,
        end_time=216.144,
    ),
    file_probe.ChapterInfo(
        num=1,
        title="02 - Jonathan Harker's Journal",
        start_time=216.0,
        end_time=395.6,
    ),
    file_probe.ChapterInfo(
        num=2,
        title="03 - Jonathan Harker's Journal",
        start_time=395.6,
        end_time=678.1,
    ),
    file_probe.ChapterInfo(
        num=3,
        title="04 - Jonathan Harker's Journal",
        start_time=678.1,
        end_time=895.7,
    ),
    file_probe.ChapterInfo(
        num=4,
        title="05 - Letters — Lucy and Mina",
        start_time=895.7,
        end_time=1005.8,
    ),
]


@pytest.fixture(scope="session", autouse=False)
def dracula_files(tmp_path_factory) -> typing.Iterator[pathlib.Path]:
    out_dir = tmp_path_factory.mktemp("dracula")

    freqs = [600, 1200]

    to_create = []
    for freq, chapter in zip(itertools.cycle(freqs), DRACULA_CHAPTERS):
        file_info = file_probe.FileInfo(
            format_info=file_probe.FormatInfo(
                filename=f"Dracula - Chapter {chapter.num:02d}.mp3",
                format_name="mp3",
                format_long_name="MP2/3 (MPEG audio layer 2/3)",
                start_time=0.0,
                duration=chapter.end_time - chapter.start_time,
                tags={
                    "title": chapter.title,
                    "description": DRACULA_DESC,
                    "comment": DRACULA_DESC,
                    "track": f"{chapter.num}",
                    "artist": "Bram Stoker",
                    "language": "English",
                    "genre": "Horror",
                    "album": "Dracula",
                },
            )
        )

        to_create.append((file_info, out_dir / file_info.format_info.filename, freq))

    with futures.ThreadPoolExecutor() as executor:
        list(executor.map(lambda args: utils.make_file(*args), to_create))

        yield out_dir


@pytest.fixture(scope="session", autouse=False)
def chaptered_frankenstein(tmp_path_factory) -> typing.Iterator[pathlib.Path]:
    out_dir = tmp_path_factory.mktemp("frankenstein")
    filename = "Mary Shelley - Frankenstein.m4b"
    ffmetadata = (
        pathlib.Path(__file__).parent
        / "data/example_media/audiobooks/Fiction/Mary Shelley - Frankenstein/frankenstein_ffmetadata.txt"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-i",
            os.fspath(ffmetadata),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=4410:cl=mono",
            "-t",
            "2981.8972",
            "-q:a",
            "9",
            "-acodec",
            "aac",
            "-map_metadata",
            "0",
            "-map",
            "1",
            os.fspath(out_dir / filename),
        ]
    )

    yield out_dir / filename


@pytest.mark.parametrize(
    "chapter_infos",
    [
        None,
        {},
        {
            pathlib.Path(f"Dracula - Chapter {chapter.num:02d}.mp3"): [
                attrs.evolve(
                    chapter,
                    start_time=0.0,
                    end_time=chapter.end_time - chapter.start_time,
                )
            ]
            for chapter in DRACULA_CHAPTERS
        },
    ],
)
def test_merge_durations(
    subtests,
    caplog,
    dracula_files: pathlib.Path,
    chapter_infos: typing.Optional[
        typing.Mapping[pathlib.Path, file_probe.ChapterInfo]
    ],
    tmp_path: pathlib.Path,
) -> None:
    out_path = tmp_path / "Dracula.m4b"
    assert not out_path.exists()

    if chapter_infos is not None:
        chapter_infos = {
            dracula_files / filename: chapter
            for filename, chapter in chapter_infos.items()
        }

    caplog.set_level(logging.WARN)

    with caplog.at_level(logging.WARN):
        m4btools.make_single_file_chaptered(
            dracula_files, out_path, chapter_info=chapter_infos
        )

        for msg in caplog.messages:
            if "Mismatch between pre-calculated chapter" in msg:
                break
        else:
            # Assert that the warning is logged if it should be, otherwise
            # assert that it is *not* logged.
            assert chapter_infos != {}

    assert out_path.exists()

    file_info = file_probe.FileInfo.from_file(out_path)
    with subtests.test("Chaptered"):
        assert file_info.chapters is not None
        assert len(file_info.chapters) == len(DRACULA_CHAPTERS)

        for actual, expected in zip(file_info.chapters, DRACULA_CHAPTERS):
            with subtests.test(f"{expected.num}: {expected.title}"):
                assert actual.title == expected.title
                assert actual.num == expected.num
                assert actual.start_time == pytest.approx(expected.start_time, abs=0.5)
                assert actual.end_time == pytest.approx(expected.end_time, abs=0.5)

    format_info = file_info.format_info
    with subtests.test("Duration"):
        assert format_info.duration == pytest.approx(
            DRACULA_CHAPTERS[-1].end_time, rel=0.1
        )

    with subtests.test("Description"):
        # For some reason "language" isn't supported in m4a
        assert format_info.tags["description"] == DRACULA_DESC
        assert format_info.tags["comment"] == DRACULA_DESC
        assert format_info.tags["artist"] == "Bram Stoker"
        assert format_info.tags["genre"] == "Horror"
        assert format_info.tags["album"] == "Dracula"


def test_merge_multifile_chapter(tmp_path: pathlib.Path, subtests) -> None:
    file1_chapters = [
        file_probe.ChapterInfo(
            num=0,
            title="Chapter 00",
            start_time=0.0,
            end_time=23.5,
        ),
        file_probe.ChapterInfo(
            num=1,
            title="Chapter 01",
            start_time=23.5,
            end_time=40.1,
        ),
    ]
    file2_chapters = [
        file_probe.ChapterInfo(
            num=2,
            title="Chapter 02",
            start_time=15.3,
            end_time=30.6,
        ),
        file_probe.ChapterInfo(
            num=3, title="Chapter 03", start_time=30.6, end_time=45.0
        ),
    ]

    format_info_base = file_probe.FormatInfo(
        format_name="mp3",
        format_long_name="MP2/3 (MPEG audio layer 2/3)",
        start_time=0.0,
        tags={
            "title": "Generic Book",
            "artist": "Author Q. Authorson",
        },
    )

    file_info_1 = file_probe.FileInfo(
        format_info=attrs.evolve(
            format_info_base, filename="Book-Part00.mp3", duration=40.1
        ),
        chapters=file1_chapters,
    )
    file_info_2 = file_probe.FileInfo(
        format_info=attrs.evolve(
            format_info_base, filename="Book-Part01.mp3", duration=45.0
        ),
        chapters=file2_chapters,
    )

    # Expected outputs
    expected_chapters = [
        file_probe.ChapterInfo(
            num=0,
            title="Chapter 00",
            start_time=0.0,
            end_time=23.5,
        ),
        file_probe.ChapterInfo(
            num=1,
            title="Chapter 01",
            start_time=23.5,
            end_time=55.4,
        ),
        file_probe.ChapterInfo(
            num=2,
            title="Chapter 02",
            start_time=55.4,
            end_time=70.7,
        ),
        file_probe.ChapterInfo(
            num=3, title="Chapter 03", start_time=70.7, end_time=85.1
        ),
    ]

    in_path = tmp_path / "in"
    out_path = tmp_path / "out" / "Joined.m4b"

    in_path.mkdir()
    out_path.parent.mkdir()

    file1 = in_path / file_info_1.format_info.filename
    file2 = in_path / file_info_2.format_info.filename
    utils.make_file(file_info_1, file1)
    utils.make_file(file_info_2, file2)

    m4btools.make_single_file_chaptered(in_path, out_path)

    out_file_info = file_probe.FileInfo.from_file(out_path)

    for actual, expected in zip(out_file_info.chapters, expected_chapters):
        with subtests.test(f"{expected.num}: {expected.title}"):
            assert actual.title == expected.title
            assert actual.num == expected.num
            assert actual.start_time == pytest.approx(expected.start_time, abs=0.5)
            assert actual.end_time == pytest.approx(expected.end_time, abs=0.5)


def test_overdrive_media_markers(tmp_path: pathlib.Path) -> None:
    in_path = tmp_path / "in"
    out_path = tmp_path / "out/joined.mp3"

    in_path.mkdir()
    out_path.parent.mkdir()

    fi1 = file_probe.FileInfo(
        format_info=file_probe.FormatInfo(
            filename="Part00.mp3",
            format_name="mp3",
            start_time=0.0,
            duration=145.6,
            tags={
                "title": "OD Book",
                "artist": "Samuel X. Author",
                "comment": "A book on overdrive.",
                "encoded_by": "OverDrive, Inc.",
                "OverDrive MediaMarkers": "<Markers>"
                + "<Marker><Name>Libraries and you</Name><Time>00:00.00</Time></Marker>"
                + "<Marker><Name>Another Chapter</Name><Time>01:15.00</Time></Marker>"
                + "</Markers>",
            },
        )
    )

    fi2 = file_probe.FileInfo(
        format_info=file_probe.FormatInfo(
            filename="Part01.mp3",
            format_name="mp3",
            start_time=0.0,
            duration=175.9,
            tags={
                "title": "OD Book",
                "artist": "Samuel X. Author",
                "comment": "A book on overdrive.",
                "encoded_by": "OverDrive, Inc.",
                "OverDrive MediaMarkers": "<Markers>"
                + "<Marker><Name>Oh hai</Name><Time>00:00.00</Time></Marker>"
                + "<Marker><Name>Time to rumble</Name><Time>00:12.50</Time></Marker>"
                + "<Marker><Name>Farewell</Name><Time>02:15.96</Time></Marker>"
                + "</Markers>",
            },
        )
    )

    expected_chapters = [
        file_probe.ChapterInfo(
            num=0, title="Libraries and you", start_time=0.0, end_time=75.0
        ),
        file_probe.ChapterInfo(
            num=1,
            title="Another Chapter",
            start_time=75.0,
            end_time=145.6,
        ),
        file_probe.ChapterInfo(
            num=2,
            title="Oh hai",
            start_time=145.6,
            end_time=158.1,
        ),
        file_probe.ChapterInfo(
            num=3, title="Time to rumble", start_time=158.1, end_time=281.56
        ),
        file_probe.ChapterInfo(
            num=4,
            title="Farewell",
            start_time=281.56,
            end_time=321.86,
        ),
    ]

    for fi in (fi1, fi2):
        utils.make_file(fi, in_path / fi.format_info.filename)

    m4btools.make_single_file_chaptered(in_path, out_path)

    actual_fi = file_probe.FileInfo.from_file(out_path)

    assert actual_fi.chapters
    assert len(actual_fi.chapters) == len(expected_chapters)

    for actual, expected in zip(actual_fi.chapters, expected_chapters):
        assert actual.title == expected.title
        assert actual.num == expected.num
        assert actual.start_time == pytest.approx(expected.start_time, abs=0.5)
        assert actual.end_time == pytest.approx(expected.end_time, abs=0.5)

        assert "OverDrive MediaMarkers" not in actual.tags

    assert "OverDrive MediaMarkers" not in actual_fi.format_info.tags


def test_make_single_file_error(tmp_path: pathlib.Path):
    in_path = tmp_path / "in"
    in_path.mkdir()

    # Create files that aren't actually mp3 files, but give them legitimate
    # file info
    fi1 = file_probe.FileInfo(
        format_info=file_probe.FormatInfo(
            filename="Part00.mp3",
            format_name="mp3",
            start_time=0.0,
            duration=20.5,
        ),
        chapters=[file_probe.ChapterInfo(num=0, start_time=0, end_time=20.5)],
    )

    fi2 = file_probe.FileInfo(
        format_info=file_probe.FormatInfo(
            filename="Part01.mp3",
            format_name="mp3",
            start_time=0.0,
            duration=40.1,
        ),
        chapters=[file_probe.ChapterInfo(num=1, start_time=0.0, end_time=40.1)],
    )

    file_infos = {}
    for fi in (fi1, fi2):
        p = in_path / fi.format_info.filename
        p.touch()
        file_infos[p] = fi

    with mock.patch.object(
        m4btools.file_probe.FileInfo, "from_file", side_effect=file_infos.get
    ):
        with pytest.raises(IOError):
            m4btools.make_single_file_chaptered(in_path, tmp_path / "out")
