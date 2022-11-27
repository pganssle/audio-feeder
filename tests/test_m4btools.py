import itertools
import logging
import os
import pathlib
import subprocess
import typing
from concurrent import futures
from unittest import mock

import attrs
import pytest

from audio_feeder import directory_parser as dp
from audio_feeder import file_probe, m4btools, segmenter

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
        end_time=21.6144,
    ),
    file_probe.ChapterInfo(
        num=1,
        title="02 - Jonathan Harker's Journal",
        start_time=21.60,
        end_time=39.56,
    ),
    file_probe.ChapterInfo(
        num=2,
        title="03 - Jonathan Harker's Journal",
        start_time=39.56,
        end_time=67.81,
    ),
    file_probe.ChapterInfo(
        num=3,
        title="04 - Jonathan Harker's Journal",
        start_time=67.81,
        end_time=89.57,
    ),
    file_probe.ChapterInfo(
        num=4,
        title="05 - Letters — Lucy and Mina",
        start_time=89.57,
        end_time=100.58,
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


FRANKENSTEIN_METADATA: typing.Final[pathlib.Path] = (
    pathlib.Path(__file__).parent
    / "data/example_media/audiobooks/Fiction/Mary Shelley - Frankenstein/frankenstein_ffmetadata.txt"
)


@pytest.fixture(scope="session", autouse=False)
def chaptered_frankenstein(tmp_path_factory) -> typing.Iterator[pathlib.Path]:
    out_dir = tmp_path_factory.mktemp("frankenstein")
    filename = "Mary Shelley - Frankenstein.m4b"
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-i",
            os.fspath(FRANKENSTEIN_METADATA),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=4410:cl=mono",
            "-t",
            "298.18972",
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


@pytest.fixture(scope="session", autouse=False)
def multifile_chaptered(tmp_path_factory) -> typing.Iterable[pathlib.Path]:
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

    in_path = (
        tmp_path_factory.mktemp("multifile_chaptered")
        / "Author Q. Authorson - Generic Book"
    )
    in_path.mkdir()

    file1 = in_path / file_info_1.format_info.filename
    file2 = in_path / file_info_2.format_info.filename
    utils.make_file(file_info_1, file1)
    utils.make_file(file_info_2, file2)

    yield in_path


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

    loader = dp.AudiobookLoader()
    files = loader.audio_files(dracula_files)
    jobs = m4btools.single_file_chaptered_jobs(
        files, out_path, chapter_info=chapter_infos
    )

    with caplog.at_level(logging.WARN):
        m4btools.render_jobs(jobs)

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


def test_merge_multifile_chaptered(
    tmp_path: pathlib.Path, multifile_chaptered: pathlib.Path, subtests
) -> None:
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

    out_path = tmp_path / "out" / "Joined.m4b"
    out_path.parent.mkdir()

    loader = dp.AudiobookLoader()
    files = loader.audio_files(multifile_chaptered)
    jobs = m4btools.single_file_chaptered_jobs(files, out_path)

    m4btools.render_jobs(jobs)

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

    loader = dp.AudiobookLoader()
    files = loader.audio_files(in_path)
    jobs = m4btools.single_file_chaptered_jobs(files, out_path)

    m4btools.render_jobs(jobs)

    actual_fi = file_probe.FileInfo.from_file(out_path)

    assert actual_fi.chapters
    assert len(actual_fi.chapters) == len(expected_chapters)

    for actual, expected in zip(actual_fi.chapters, expected_chapters):
        assert actual.title == expected.title
        assert actual.num == expected.num
        assert actual.start_time == pytest.approx(expected.start_time, abs=0.5)
        assert actual.end_time == pytest.approx(expected.end_time, abs=0.5)


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

    loader = dp.AudiobookLoader()
    files = loader.audio_files(in_path)

    with mock.patch.object(
        m4btools.file_probe.FileInfo, "from_file", side_effect=file_infos.get
    ):
        jobs = m4btools.single_file_chaptered_jobs(files, tmp_path / "out")

        with pytest.raises(IOError):
            m4btools.render_jobs(jobs)


def test_split_chapters_onefile(
    chaptered_frankenstein: pathlib.Path, tmp_path: pathlib.Path
):
    out_dir = tmp_path / "Mary Shelley - Frankenstein"
    expected_chap_data = (
        (0, 21.93043, "00 - Letters"),
        (21.93043, 28.24019, "Chapter 1"),
        (28.24019, 38.52025, "Chapter 2"),
        (38.52025, 48.41000, "Chapter 3"),
        (48.41000, 57.63025, "Chapter 4"),
        (57.63025, 67.92015, "Chapter 5"),
        (67.92015, 79.66045, "Chapter 6"),
        (79.66045, 92.71013, "Chapter 7"),
        (92.71013, 105.07043, "Chapter 8"),
        (105.07043, 113.32009, "Chapter 9"),
        (113.32009, 123.18039, "Chapter 10"),
        (123.18039, 133.83004, "Chapter 11"),
        (133.83004, 142.09030, "Chapter 12"),
        (142.09030, 150.12036, "Chapter 13"),
        (150.12036, 156.10036, "Chapter 14"),
        (156.10036, 166.41005, "Chapter 15"),
        (166.41005, 179.74014, "Chapter 16"),
        (179.74014, 187.87005, "Chapter 17"),
        (187.87005, 199.79016, "Chapter 18"),
        (199.79016, 209.88010, "Chapter 19"),
        (209.88010, 224.87003, "Chapter 20"),
        (224.87003, 237.51000, "Chapter 21"),
        (237.51000, 249.38024, "Chapter 22"),
        (249.38024, 261.04031, "Chapter 23"),
        (261.04031, 298.18972, "Chapter 24"),
    )

    expected_chapters = []
    for i, (start_time, end_time, chapter_title) in enumerate(expected_chap_data):
        expected_chapters.append(
            file_probe.ChapterInfo(
                num=i, start_time=0, end_time=end_time - start_time, title=chapter_title
            )
        )

    out_dir.mkdir()
    loader = dp.AudiobookLoader()
    files = loader.audio_files(chaptered_frankenstein.parent)

    jobs = m4btools.chapter_split_jobs(files, out_dir, base_name="Frankenstein")
    m4btools.render_jobs(jobs)

    files = loader.audio_files(out_dir)

    actual_chapters = file_probe.get_multipath_chapter_info(files)
    assert len(files) == len(expected_chapters)

    for (file_path, actual_chapter), expected_chapter in zip(
        actual_chapters, expected_chapters
    ):
        assert file_path.suffix == ".m4b"
        assert actual_chapter.num == expected_chapter.num
        assert actual_chapter.title == expected_chapter.title
        assert actual_chapter.start_time == pytest.approx(
            expected_chapter.start_time, abs=0.5
        )
        assert actual_chapter.end_time == pytest.approx(
            expected_chapter.end_time, abs=0.5
        )


def test_split_chapters_multifile(
    multifile_chaptered: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    out_path = tmp_path

    expected_results = [
        (
            "Generic Book - 0.mp3",
            file_probe.ChapterInfo(
                title="Chapter 00", num=0, start_time=0.0, end_time=23.5
            ),
        ),
        (
            "Generic Book - 1.mp3",
            file_probe.ChapterInfo(
                title="Chapter 01", num=1, start_time=0.0, end_time=31.9
            ),
        ),
        (
            "Generic Book - 2.mp3",
            file_probe.ChapterInfo(
                title="Chapter 02", num=2, start_time=0.0, end_time=15.3
            ),
        ),
        (
            "Generic Book - 3.mp3",
            file_probe.ChapterInfo(
                title="Chapter 03", num=3, start_time=0.0, end_time=14.4
            ),
        ),
    ]

    loader = dp.AudiobookLoader()
    files = loader.audio_files(multifile_chaptered)
    jobs = m4btools.chapter_split_jobs(files, out_path, base_name="Generic Book - ")
    m4btools.render_jobs(jobs)

    actual_results = file_probe.get_multipath_chapter_info(
        loader.audio_files(out_path), fall_back_to_durations=False
    )
    assert len(actual_results) == len(expected_results)
    for (actual_file, actual_chapter), (expected_file, expected_chapter) in zip(
        actual_results, expected_results
    ):
        assert actual_file.name == expected_file

        assert actual_chapter.title == expected_chapter.title
        assert actual_chapter.num == expected_chapter.num
        assert actual_chapter.start_time == pytest.approx(
            expected_chapter.start_time, abs=0.5
        )
        assert actual_chapter.end_time == pytest.approx(
            expected_chapter.end_time, abs=0.5
        )


def test_segmenter_already_optimal(tmp_path: pathlib.Path) -> None:
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
            format_info_base, filename="Book-Part00.mp3", duration=60.0
        )
    )
    file_info_2 = file_probe.FileInfo(
        format_info=attrs.evolve(
            format_info_base, filename="Book-Part01.mp3", duration=60.0
        )
    )

    in_path = tmp_path / "in_path"
    in_path.mkdir()

    out_path = tmp_path / "out_path"
    out_path.mkdir()

    for fi in (file_info_1, file_info_2):
        utils.make_file(fi, in_path / fi.format_info.filename)

    loader = dp.AudiobookLoader()
    files = loader.audio_files(in_path)
    jobs = m4btools.segment_files_jobs(
        files, out_path, cost_func=segmenter.asymmetric_cost(60.0)
    )

    copy_only = [job.is_copy_job() for job in jobs]
    assert copy_only == [True, True]


def test_segmenter_split_single_file(
    chaptered_frankenstein: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    expected_chap_data = (
        (
            57.63025,
            (
                (0, 21.93043, "00 - Letters"),
                (21.93043, 28.24019, "Chapter 1"),
                (28.24019, 38.52025, "Chapter 2"),
                (38.52025, 48.41, "Chapter 3"),
                (48.41, 57.63025, "Chapter 4"),
            ),
        ),
        (
            65.55014,
            (
                (0.0, 10.28990000000001, "Chapter 5"),
                (10.28990000000001, 22.0302, "Chapter 6"),
                (22.0302, 35.07988000000001, "Chapter 7"),
                (35.07988000000001, 47.440180000000005, "Chapter 8"),
                (47.440180000000005, 55.68984, "Chapter 9"),
                (55.68984, 65.55014, "Chapter 10"),
            ),
        ),
        (
            56.559749999999994,
            (
                (0.0, 10.649649999999994, "Chapter 11"),
                (10.649649999999994, 18.90991000000001, "Chapter 12"),
                (18.90991000000001, 26.939970000000002, "Chapter 13"),
                (26.939970000000002, 32.91996999999999, "Chapter 14"),
                (32.91996999999999, 43.22966000000001, "Chapter 15"),
                (43.22966000000001, 56.559749999999994, "Chapter 16"),
            ),
        ),
        (
            57.769859999999994,
            (
                (0.0, 8.129909999999995, "Chapter 17"),
                (8.129909999999995, 20.05001999999999, "Chapter 18"),
                (20.05001999999999, 30.139960000000002, "Chapter 19"),
                (30.139960000000002, 45.12989000000002, "Chapter 20"),
                (45.12989000000002, 57.769859999999994, "Chapter 21"),
            ),
        ),
        (
            60.67972000000003,
            (
                (0.0, 11.870239999999995, "Chapter 22"),
                (11.870239999999995, 23.530309999999986, "Chapter 23"),
                (23.530309999999986, 60.67972000000003, "Chapter 24"),
            ),
        ),
    )

    expected_results = []
    chap_num = 0
    for duration, chapter_data in expected_chap_data:
        chapter_infos: typing.MutableSequence = []
        for start, end, chapter_title in chapter_data:
            chapter_infos.append(
                file_probe.ChapterInfo(
                    start_time=start, end_time=end, title=chapter_title, num=chap_num
                )
            )
            chap_num += 1

        expected_results.append((duration, tuple(chapter_infos)))

    out_path = tmp_path / "out"
    out_path.mkdir()

    jobs = m4btools.segment_files_jobs(
        [chaptered_frankenstein],
        out_path,
        cost_func=segmenter.asymmetric_cost(60.0),
    )

    m4btools.render_jobs(jobs)

    loader = dp.AudiobookLoader()
    actual_file_infos = tuple(
        map(file_probe.FileInfo.from_file, loader.audio_files(out_path))
    )

    assert len(actual_file_infos) == len(expected_results)

    for actual, (duration, chapters) in zip(actual_file_infos, expected_results):
        assert actual.format_info.duration == pytest.approx(duration, abs=0.25)

        assert actual.chapters is not None
        assert len(actual.chapters) == len(chapters)
        for actual_chapter, expected_chapter in zip(actual.chapters, chapters):
            # Not sure how to accomplish this
            # assert actual_chapter.num == expected_chapter.num
            assert actual_chapter.title == expected_chapter.title
            assert actual_chapter.start_time == pytest.approx(
                expected_chapter.start_time, abs=0.25
            )
            assert actual_chapter.end_time == pytest.approx(
                expected_chapter.end_time, abs=0.25
            )
