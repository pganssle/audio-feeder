"""Tests for audio_feeder.page_generator"""

import datetime
import pathlib
from collections.abc import Sequence

import hypothesis
import pytest
from hypothesis import strategies as st

from audio_feeder import file_probe
from audio_feeder import object_handler as oh
from audio_feeder import page_generator as pg
from audio_feeder import resolver
from audio_feeder._db_types import ID


def test_load_type_without_templates(testgen_config: pathlib.Path) -> None:
    renderer = pg.EntryRenderer(resolver.get_resolver())
    (renderer.entry_templates_loc / "empty_type").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="empty_type"):
        renderer.load_type("empty_type")


@pytest.mark.parametrize(
    "params, expected_url",
    [
        ({"page": 2, "perPage": 25}, "/books?page=2&perPage=25"),
        (
            {"folder": "Fiction/Science & Nature"},
            "/books?folder=Fiction%2FScience+%26+Nature",
        ),
        ({"q": "a=b?c#d"}, "/books?q=a%3Db%3Fc%23d"),
    ],
)
def test_nav_item_url_encodes_params(
    params: dict[str, object], expected_url: str
) -> None:
    assert pg.NavItem("/books", "1", params=params).url == expected_url


def test_nav_item_without_params() -> None:
    assert pg.NavItem("/books", "1").url == "/books"
    assert pg.NavItem("/books", "1", params={"page": 2}).display_only().url is None


def test_nav_item_kinds() -> None:
    assert pg.NavItem("/books", "1").kind is pg.NavKind.LINK
    assert pg.NavItem("/books", "1").display_only().kind is pg.NavKind.CURRENT
    gap = pg.NavItem.gap()
    assert (gap.kind, gap.url, gap.display) == (pg.NavKind.GAP, None, "…")


@pytest.mark.parametrize(
    "num_pages, current, expected",
    [
        (0, 0, ()),
        (1, 0, (0,)),
        (2, 1, (0, 1)),
        # Few enough pages that every page is shown
        (7, 0, (0, 1, 2, 3, 4, 5, 6)),
        (8, 3, (0, 1, 2, 3, 4, 5, 6, 7)),
        (8, 4, (0, 1, 2, 3, 4, 5, 6, 7)),
        # An ellipsis standing in for two pages still saves some room
        (8, 0, (0, 1, 2, None, 5, 6, 7)),
        # Current page at the start or end
        (20, 0, (0, 1, 2, None, 17, 18, 19)),
        (20, 19, (0, 1, 2, None, 17, 18, 19)),
        (20, 3, (0, 1, 2, 3, 4, None, 17, 18, 19)),
        # Current page in the middle
        (20, 10, (0, 1, 2, None, 9, 10, 11, None, 17, 18, 19)),
        # A gap of exactly one page shows the page rather than an ellipsis
        (20, 5, (0, 1, 2, 3, 4, 5, 6, None, 17, 18, 19)),
        (20, 14, (0, 1, 2, None, 13, 14, 15, 16, 17, 18, 19)),
        # A gap of two pages is an ellipsis
        (20, 6, (0, 1, 2, None, 5, 6, 7, None, 17, 18, 19)),
        # A current page past the end doesn't add anything
        (20, 25, (0, 1, 2, None, 17, 18, 19)),
    ],
)
def test_page_window(
    num_pages: int, current: int, expected: Sequence[int | None]
) -> None:
    assert pg.page_window(num_pages, current) == expected


def test_page_window_custom_sizes() -> None:
    assert pg.page_window(20, 10, edge=1, around=2) == (
        0, None, 8, 9, 10, 11, 12, None, 19,
    )  # fmt: skip


@hypothesis.given(
    num_pages=st.integers(min_value=1, max_value=200),
    data=st.data(),
    edge=st.integers(min_value=1, max_value=5),
    around=st.integers(min_value=0, max_value=5),
)
def test_page_window_properties(
    num_pages: int, data: st.DataObject, edge: int, around: int
) -> None:
    current = data.draw(st.integers(min_value=0, max_value=num_pages - 1))
    window = pg.page_window(num_pages, current, edge=edge, around=around)
    pages = [page for page in window if page is not None]

    assert pages == sorted(set(pages))
    assert {0, current, num_pages - 1} <= set(pages)
    assert len(window) <= 2 * edge + 2 * around + 3
    # Every gap stands in for at least two pages
    for index, page in enumerate(window):
        if page is None:
            before, after = window[index - 1], window[index + 1]
            assert before is not None and after is not None
            assert after - before > 2


def test_windowed_nav() -> None:
    nav_list = [pg.NavItem("/books", str(ii), params={"page": ii}) for ii in range(20)]
    nav_list[10] = nav_list[10].display_only()

    window = pg.windowed_nav(nav_list, 10)

    assert [item.display for item in window] == [
        "0", "1", "2", "…", "9", "10", "11", "…", "17", "18", "19",
    ]  # fmt: skip
    assert [item.kind for item in window].count(pg.NavKind.GAP) == 2
    assert window[5] is nav_list[10]
    assert window[5].kind is pg.NavKind.CURRENT


def _labels(keys: Sequence[pg.SortKey], per_page: int) -> Sequence[str]:
    return tuple(map(str, pg.page_range_labels(keys, per_page, lambda key: key)))


@pytest.mark.parametrize(
    "keys, per_page, expected",
    [
        ([], 2, ()),
        # Text is shortened to two characters when that distinguishes it
        (
            ["Aaron", "Atwood", "Austen", "Bronte", "Byron", "Carroll"],
            2,
            ("Aa → At", "Au → Br", "By → Ca"),
        ),
        # ...and lengthened when the neighbouring boundaries share a prefix
        (
            ["Dickens", "Dickinson", "Dickson", "Doyle"],
            2,
            ("Dicke → Dicki", "Dicks → Do"),
        ),
        # A page with a single entry, or only one key, is labelled once
        (["Austen", "Bronte", "Carroll"], 2, ("Au → Br", "Ca")),
        (["Austen", "Austen", "Bronte"], 2, ("Au", "Br")),
        # The same key either side of a page boundary can't be told apart, so
        # it doesn't make the label any longer.
        (
            ["Austen", "Dickens", "Dickens", "Eliot"],
            2,
            ("Au → Di", "Di → El"),
        ),
        # Labels are never longer than MAX_LABEL_PREFIX
        (
            ["Abcdefghijklmnopqrs", "Abcdefghijklmnopqrt"],
            1,
            ("Abcdefghijkl", "Abcdefghijkl"),
        ),
        # Short keys, and keys on single-entry pages
        (["A", "B b", "B c"], 1, ("A", "B b", "B c")),
        # Trailing spaces are dropped
        (["Ab cd", "Abc"], 2, ("Ab \u2192 Abc",)),
        # Equal keys always get the same label, even across pages
        (
            ["Austen", "Dickens", "Dickens", "Dickens", "Dickinson"],
            2,
            ("Au \u2192 Dicke", "Dicke", "Dicki"),
        ),
        # Descending order
        (["Carroll", "Byron", "Austen"], 2, ("Ca → By", "Au")),
        # Missing keys
        ([None, "", "Austen"], 1, ("?", "?", "Au")),
    ],
)
def test_page_range_labels_text(
    keys: Sequence[pg.SortKey], per_page: int, expected: Sequence[str]
) -> None:
    assert _labels(keys, per_page) == expected


@pytest.mark.parametrize(
    "start, end, expected",
    [
        # Each range leaves out what both ends have in common
        (datetime.date(2023, 3, 12), datetime.date(2023, 3, 12), ("12 Mar 2023", None)),
        (datetime.date(2023, 3, 3), datetime.date(2023, 3, 17), ("3", "17 Mar 2023")),
        (
            datetime.date(2023, 3, 3),
            datetime.date(2023, 6, 17),
            ("3 Mar", "17 Jun 2023"),
        ),
        # Ranges across years only give the months
        (
            datetime.date(2022, 12, 3),
            datetime.date(2023, 2, 1),
            ("Dec 2022", "Feb 2023"),
        ),
        # Descending order
        (
            datetime.date(2023, 6, 17),
            datetime.date(2023, 3, 3),
            ("17 Jun", "3 Mar 2023"),
        ),
        # Times are ignored
        (
            datetime.datetime(2024, 1, 2, 23, 59, tzinfo=datetime.UTC),
            datetime.datetime(2024, 1, 2, 0, 0, tzinfo=datetime.UTC),
            ("2 Jan 2024", None),
        ),
    ],
)
def test_page_range_labels_dates(
    start: datetime.date, end: datetime.date, expected: tuple[str, str | None]
) -> None:
    (page_range,) = pg.page_range_labels([start, end], 2, lambda key: key)
    assert (page_range.start, page_range.end) == expected


def test_page_range_labels_missing_dates() -> None:
    keys = [datetime.date(2023, 6, 1), None, None]
    assert _labels(keys, 2) == ("1 Jun 2023 \u2192 ?", "?")


def test_page_range_labels_only_reads_page_boundaries() -> None:
    keys = [f"Author {ii:04}" for ii in range(100)]
    seen: list[int] = []

    def key(index: int) -> str:
        seen.append(index)
        return keys[index]

    labels = pg.page_range_labels(range(100), 25, key)

    assert len(labels) == 4
    assert sorted(seen) == [0, 24, 25, 49, 50, 74, 75, 99]


def _file_info(*chapter_starts: float) -> file_probe.FileInfo:
    """A minute long file with chapters starting at these times."""
    return file_probe.FileInfo(
        format_info=file_probe.FormatInfo(duration=60.0),
        chapters=[
            file_probe.ChapterInfo(num=num, start_time=start, end_time=start + 10)
            for num, start in enumerate(chapter_starts, 1)
        ],
    )


@pytest.mark.parametrize(
    "file_infos, has_chapter_info, broken_chapter_info",
    [
        (None, False, False),
        ((), False, False),
        ((_file_info(), _file_info()), False, False),
        ((_file_info(0.0, 30.0), _file_info()), True, False),
        ((_file_info(0.0, 30.0), _file_info(0.0, 30.0)), True, False),
        # Broken chapter information is still chapter information, so the
        # book list links to the chapters feed and says that it's broken
        ((_file_info(0.0, 30.0), _file_info(0.0, 90.0)), True, True),
        ((_file_info(), _file_info(0.0, 90.0)), True, True),
        ((_file_info(90.0),), True, True),
    ],
)
def test_render_chapter_info(
    testgen_config: pathlib.Path,
    file_infos: Sequence[file_probe.FileInfo] | None,
    has_chapter_info: bool,
    broken_chapter_info: bool,
) -> None:
    files = None
    file_metadata = None
    if file_infos is not None:
        files = [pathlib.Path(f"Part{i:02}.mp3") for i in range(len(file_infos))]
        file_metadata = dict(zip(files, file_infos))

    entry = oh.Entry(
        id=ID(1),
        path=pathlib.Path("Book"),
        type="Book",
        data_id=ID(1),
        files=files,
        file_metadata=file_metadata,
    )
    rendered = pg.EntryRenderer(resolver.get_resolver()).render(
        entry, oh.Book(id=ID(1), title="Book", authors=["Some Author"])
    )

    assert rendered["has_chapter_info"] is has_chapter_info
    assert rendered["broken_chapter_info"] is broken_chapter_info
    assert ("CHAPTERS" in rendered["rendered_qr_img_urls"]) is has_chapter_info
