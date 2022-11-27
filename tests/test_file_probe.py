import datetime
import logging
import pathlib
import typing

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
    ],
)
def test_bad_overdrive_media_tags(tag: str, err_type: typing.Type[Exception]) -> None:
    with pytest.raises(err_type):
        file_probe.OverdriveMediaMarker.from_xml(tag)
