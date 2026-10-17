import datetime
import logging
import pathlib
from collections.abc import Sequence

import pytest

from audio_feeder import file_probe

from . import utils


def test_get_multipath_chapter_info(tmp_path: pathlib.Path) -> None:
    expected_chapters = [
        file_probe.ChapterInfo(
            num=0,
            start_time=0.0,
            end_time=20.5,
            title="Hi",
            tags={"artist": "Some Guy"},
        ),
        file_probe.ChapterInfo(
            num=1,
            start_time=0.0,
            end_time=12.5,
            title="Yo",
            tags={"artist": "Some Guy"},
        ),
        file_probe.ChapterInfo(
            num=2,
            start_time=12.5,
            end_time=22.9,
            title="Someone different!",
            tags={"artist": "Some Guy, Jr."},
        ),
    ]

    fi1 = file_probe.FileInfo(
        format_info=file_probe.FormatInfo(
            filename="Part00.mp3",
            format_name="mp3",
            start_time=0.0,
            duration=20.5,
        ),
        chapters=[expected_chapters[0]],
    )

    fi2 = file_probe.FileInfo(
        format_info=file_probe.FormatInfo(
            filename="Part01.mp3",
            format_name="mp3",
            start_time=0.0,
            duration=22.9,
        ),
        chapters=[*expected_chapters[1:]],
    )

    file1 = tmp_path / fi1.format_info.filename
    file2 = tmp_path / fi2.format_info.filename

    expected = [
        (file1, expected_chapters[0]),
        (file2, expected_chapters[1]),
        (file2, expected_chapters[2]),
    ]

    for fi, filepath in [(fi1, file1), (fi2, file2)]:
        utils.make_file(fi, filepath)

    actual = file_probe.get_multipath_chapter_info(sorted(tmp_path.iterdir()))

    assert len(actual) == len(expected)
    for (actual_path, actual_chapters), (expected_path, expected_chapters) in zip(
        actual, expected
    ):
        assert actual_path == expected_path
        assert actual_chapters == expected_chapters


def test_chapter_info_no_tags():
    chapter_json = {
        "id": 9,
        "start_time": "122.3",
        "end_time": "209.6",
    }

    chapter_info = file_probe.ChapterInfo.from_json(chapter_json)

    assert chapter_info.num == 9
    assert chapter_info.start_time == 122.3
    assert chapter_info.end_time == 209.6
    assert chapter_info.title is None
    assert chapter_info.tags == {}


@pytest.mark.parametrize("duration", (30, 125.6))
def test_get_file_duration(duration: float, tmp_path: pathlib.Path) -> None:
    fi = file_probe.FileInfo(
        format_info=file_probe.FormatInfo(
            filename="example.mp3",
            format_name="mp3",
            format_long_name="MP2/3 (MPEG audio layer 2/3)",
            start_time=0.0,
            duration=duration,
        )
    )

    out_path = tmp_path / fi.format_info.filename
    utils.make_file(fi, out_path=out_path)
    duration_seconds = file_probe.get_file_duration(out_path) / datetime.timedelta(
        seconds=1
    )
    assert duration_seconds == pytest.approx(duration, abs=0.5)


def test_get_file_duration_error(tmp_path: pathlib.Path, caplog):
    file_doesnt_exist = tmp_path / "myfile.mp3"

    with caplog.at_level(logging.WARN):
        assert file_probe.get_file_duration(file_doesnt_exist) is None
        assert "Failed to get duration" in caplog.text
        assert file_doesnt_exist.name in caplog.text


@pytest.mark.parametrize(
    "tag, err_type",
    [
        (
            "<Marker><Name>No root element</Name><Time>00:00.00</Time></Marker>",
            ValueError,
        ),
        (
            "<Markers><Marker><Name>Bad time</Name>"
            + "<Time>00:00:00:00.000</Time></Marker></Markers>",
            ValueError,
        ),
        (
            "<Markers><Marker><Name>No time</Name></Marker></Markers>",
            ValueError,
        ),
    ],
)
def test_bad_overdrive_media_tags(tag: str, err_type: type[Exception]) -> None:
    with pytest.raises(err_type):
        file_probe.OverdriveMediaMarker.from_xml(tag)


def _file_info(
    chapter_times: Sequence[tuple[float, float]] | None, duration: float | None = 60.0
) -> file_probe.FileInfo:
    return file_probe.FileInfo(
        format_info=file_probe.FormatInfo(filename="file.mp3", duration=duration),
        chapters=(
            None
            if chapter_times is None
            else [
                file_probe.ChapterInfo(num=num, start_time=start, end_time=end)
                for num, (start, end) in enumerate(chapter_times, 1)
            ]
        ),
    )


@pytest.mark.parametrize(
    "file_info, broken",
    [
        # No chapter information isn't broken chapter information
        (_file_info(None), False),
        (_file_info(()), False),
        (_file_info(((0.0, 30.0), (30.0, 60.0))), False),
        # Only chapters that start after the end of the file are broken
        (_file_info(((0.0, 30.0), (30.0, 90.0))), False),
        (_file_info(((0.0, 30.0), (60.0, 60.0))), False),
        (_file_info(((0.0, 30.0), (60.5, 90.0))), True),
        (_file_info(((0.0, 120.0), (120.0, 240.0))), True),
        (_file_info(((120.0, 240.0), (0.0, 120.0))), True),
        # Without the file's duration, there's nothing to compare to
        (_file_info(((0.0, 120.0), (120.0, 240.0)), duration=None), False),
    ],
)
def test_has_broken_chapters(file_info: file_probe.FileInfo, broken: bool) -> None:
    assert file_probe.has_broken_chapters(file_info) is broken


@pytest.mark.parametrize(
    "chapter_times, usable",
    [
        (None, False),
        ((), False),
        (((0.0, 30.0), (30.0, 60.0)), True),
        (((0.0, 30.0), (60.5, 90.0)), False),
    ],
)
@pytest.mark.parametrize("fall_back_to_durations", [False, True])
def test_get_multipath_chapter_info_unusable_chapters(
    chapter_times: Sequence[tuple[float, float]] | None,
    usable: bool,
    fall_back_to_durations: bool,
) -> None:
    # Files without usable chapter information are a single chapter, if
    # they're included at all
    path = pathlib.Path("file.mp3")
    file_info = _file_info(chapter_times)

    chapter_info = file_probe.get_multipath_chapter_info(
        [path],
        file_infos={path: file_info},
        fall_back_to_durations=fall_back_to_durations,
    )

    if usable:
        assert [chapter for _, chapter in chapter_info] == file_info.chapters
    elif fall_back_to_durations:
        assert [(c.start_time, c.end_time) for _, c in chapter_info] == [(0, 60.0)]
    else:
        assert chapter_info == []
