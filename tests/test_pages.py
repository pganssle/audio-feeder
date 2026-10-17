"""Tests for audio_feeder.pages"""

import datetime
import html
import html.parser
import pathlib
import re
import shutil
import threading
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Mapping, Sequence
from urllib.parse import unquote, urlencode

import flask.testing
import pytest

from audio_feeder import app as af_app
from audio_feeder import database_handler as dh
from audio_feeder import object_handler as oh
from audio_feeder import pages, updater
from audio_feeder._db_types import ID

from . import test_updater

FICTION = ("Dracula", "The Invisible Man", "Little Women", "Little Men", "Frankenstein")
NONFICTION = (
    "How to Decode CMYK Images",
    "The Writing of Fiction",
    "Confessions of an English Opium Eater",
)


@pytest.mark.parametrize(
    "args, expected_per_page",
    [
        ({}, 25),
        ({"perPage": "10"}, 10),
        ({"perPage": "not-a-number"}, 25),
    ],
)
def test_sortable_args_per_page(
    args: Mapping[str, str], expected_per_page: int
) -> None:
    assert pages.get_sortable_args(args)["perPage"] == expected_per_page


def _entry_objects(
    title: str | None,
    authors: Sequence[tuple[str, str | None]] = (),
    series: tuple[str, int | None] | None = None,
) -> pages.EntryObjects:
    """An (entry, book, authors) triple; authors are (name, sort_name) pairs."""
    series_name, series_number = series if series is not None else (None, None)
    return (
        oh.Entry(id=ID(1), path=pathlib.Path("Book"), data_id=ID(1)),
        oh.Book(
            id=ID(1),
            title=title,
            # In practice these are a single string and integer
            series_name=series_name,  # type: ignore[arg-type]
            series_number=series_number,  # type: ignore[arg-type]
        ),
        tuple(
            oh.Author(id=ID(i), name=name, sort_name=sort_name)
            for i, (name, sort_name) in enumerate(authors)
        ),
    )


def _sorted_titles(
    entry_objects: Sequence[pages.EntryObjects], order_by: str, ascending: bool = True
) -> Sequence[str | None]:
    # Sort a reversed copy, so that a no-op sort can't pass
    return [
        book.title
        for _, book, _ in pages.sort_entry_objects(
            reversed(entry_objects), order_by=order_by, ascending=ascending
        )
    ]


@pytest.mark.parametrize(
    "order_by, entry_objects",
    [
        pytest.param(
            "author",
            (
                _entry_objects("Perdido Street Station", [("", "Miéville, China")]),
                _entry_objects("Ghost in the Wires", [("", "Mitnick, Kevin")]),
                # Lower case sorts with upper case, not after it
                _entry_objects("Whatever", [("van der Whatever", None)]),
                _entry_objects("Germinal", [("Émile Zola", "Zola, Émile")]),
            ),
            id="author",
        ),
        pytest.param(
            "author",
            (
                _entry_objects("No Author"),
                _entry_objects("Some Author", [("Someone", None)]),
            ),
            id="author-missing",
        ),
        pytest.param(
            "author",
            (
                # Books with no series sort before books in a series
                _entry_objects("Standalone", [("A", None)]),
                _entry_objects("Jo's Boys", [("A", None)], ("Little Women", None)),
                _entry_objects("Little Women", [("A", None)], ("Little Women", 2)),
                _entry_objects("Little Men", [("A", None)], ("Little Women", 10)),
                _entry_objects("Ma", [("A", None)], ("mainly", 1)),
            ),
            id="series",
        ),
        pytest.param(
            "title",
            (
                _entry_objects(None),
                _entry_objects("a Tale of Two Cities"),
                _entry_objects("Book 2"),
                _entry_objects("Book 10"),
                _entry_objects("Émile"),
                _entry_objects("Emile Zola"),
            ),
            id="title",
        ),
        pytest.param(
            "title",
            (
                _entry_objects("EMILE"),
                _entry_objects("Emile"),
                _entry_objects("Émile"),
            ),
            id="title-tie",
        ),
    ],
)
def test_sort_entry_objects(
    order_by: str, entry_objects: Sequence[pages.EntryObjects]
) -> None:
    expected = [book.title for _, book, _ in entry_objects]
    assert _sorted_titles(entry_objects, order_by) == expected
    assert _sorted_titles(entry_objects, order_by, ascending=False) == expected[::-1]


def test_sort_entry_objects_invalid_order() -> None:
    with pytest.raises(ValueError):
        pages.sort_entry_objects([_entry_objects("Book")], order_by="color")


@pytest.fixture
def client(testgen_config: pathlib.Path) -> Iterator[flask.testing.FlaskClient]:
    with test_updater.patch_book_updater():
        updater.update(content_type="books")

    app = af_app.create_app(load_db=True, populate_qr_cache=False, block=True)
    # Wait for the database to finish loading in the background. This joins
    # only that thread, since e.g. idle executor threads may never exit.
    for thread in threading.enumerate():
        if thread.name.endswith("(warm_caches)"):
            thread.join()

    yield app.test_client()


def _books(client: flask.testing.FlaskClient, **params: str | Sequence[str]) -> str:
    response = client.get("/books?" + urlencode(params, doseq=True))
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _listed(page: str) -> set[str]:
    """The titles of the books listed on a page.

    This looks at the entry titles rather than the whole page, since
    descriptions can mention other books' titles.
    """
    return {
        html.unescape(title)
        for title in re.findall(r'<span class="book_title">([^<]*)</span>', page)
    }


class _InputParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inputs: list[Mapping[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "input":
            self.inputs.append(dict(attrs))


def _checkbox_inputs(page: str, name: str) -> list[Mapping[str, str | None]]:
    """The attributes of the checkboxes named ``name``, in order."""
    parser = _InputParser()
    parser.feed(page)
    return [
        attrs
        for attrs in parser.inputs
        if attrs.get("type") == "checkbox" and attrs.get("name") == name
    ]


def _checked(page: str, name: str) -> set[str]:
    """The values of the checked checkboxes named ``name``."""
    return {
        attrs["value"] or ""
        for attrs in _checkbox_inputs(page, name)
        if "checked" in attrs
    }


def _checkboxes(page: str, name: str) -> list[str]:
    """The values of all the checkboxes named ``name``, in order."""
    return [attrs["value"] or "" for attrs in _checkbox_inputs(page, name)]


def _folder_counts(page: str) -> dict[str, int]:
    """The top-level folders in the browse drawer's folder tree."""
    match = re.search(r'<ul class="folder_tree[^"]*">(.*?)<summary>Filters', page, re.S)
    if match is None:
        return {}
    # Top-level rows are the first row in each top-level <li>
    tree = match.group(1)
    counts = {}
    depth = 0
    for token in re.finditer(
        r'(<ul>|</ul>)|<span class="row_name">([^<]*)</span>'
        r'<span class="row_count">(\d+)</span>',
        tree,
    ):
        if token.group(1) == "<ul>":
            depth += 1
        elif token.group(1) == "</ul>":
            depth -= 1
        elif depth == 0:
            counts[html.unescape(token.group(2))] = int(token.group(3))
    return counts


def test_books_unfiltered(client: flask.testing.FlaskClient) -> None:
    page = _books(client)
    assert _listed(page) == set(FICTION + NONFICTION)

    # Every book is below audiobooks/, so the folder tree starts at its
    # subfolders
    assert _folder_counts(page) == {"Fiction": 5, "Nonfiction": 3}

    # With no folder selected, there are no breadcrumbs
    assert 'class="breadcrumb' not in page


@pytest.mark.parametrize(
    "folder, expected",
    [
        ("audiobooks/Fiction", FICTION),
        ("audiobooks/Nonfiction", NONFICTION),
        ("/audiobooks/Nonfiction/", NONFICTION),
        ("audiobooks", FICTION + NONFICTION),
        ("Nonexistent", ()),
    ],
)
def test_books_filtered_by_folder(
    client: flask.testing.FlaskClient, folder: str, expected: tuple[str, ...]
) -> None:
    page = _books(client, folder=folder)
    assert _listed(page) == set(expected)


def test_books_folder_navigation(client: flask.testing.FlaskClient) -> None:
    page = _books(client, folder="audiobooks/Fiction", orderBy="title", page="0")

    # Breadcrumbs link back up, and the current folder isn't a link
    assert '<span class="breadcrumb current_folder">Fiction</span>' in page
    assert ">All</a>" in page

    # Every book is below audiobooks/, so it's left out
    assert ">audiobooks</a>" not in page
    assert "<title>Books: Fiction: Page 0 of 0</title>" in page

    # The browse drawer keeps the folder filter
    assert _checked(page, "folder") == {"audiobooks/Fiction"}

    # Folder links keep the sort order
    assert "orderBy=title" in page.split('class="breadcrumb"', 1)[1].split(">", 1)[0]


def test_books_pagination_keeps_folder(client: flask.testing.FlaskClient) -> None:
    page = _books(client, folder="audiobooks/Fiction", perPage="2")

    assert "folder=audiobooks%2FFiction" in page
    # 5 Fiction books at 2 per page is 3 pages
    assert "Page 0 of 2" in page


def test_books_invalid_folder_is_ignored(client: flask.testing.FlaskClient) -> None:
    page = _books(client, folder="../secrets")
    assert _listed(page) == set(FICTION + NONFICTION)


def _titles_by_tag() -> dict[str, set[str]]:
    books = dh.get_database()["books"].values()
    by_tag: dict[str, set[str]] = {}
    for book in books:
        for tag in book.tags or ():
            by_tag.setdefault(tag.casefold(), set()).add(book.title)
    return by_tag


def test_books_filtered_by_author(client: flask.testing.FlaskClient) -> None:
    page = _books(client, author="ALCOTT")
    assert _listed(page) == {"Little Women", "Little Men"}

    assert re.search(r'name="author"\s+value="ALCOTT"', page)


def test_books_filtered_by_tag(client: flask.testing.FlaskClient) -> None:
    by_tag = _titles_by_tag()
    # Google Books categories from the recorded responses become tags
    assert by_tag

    for tag, titles in by_tag.items():
        page = _books(client, tag=tag, perPage="100")
        assert _listed(page) == titles, tag


def test_books_filtered_by_date_added(client: flask.testing.FlaskClient) -> None:
    tomorrow = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)).date()

    page = _books(client, addedSince=tomorrow.isoformat())
    assert not _listed(page)

    page = _books(client, addedBefore=tomorrow.isoformat())
    assert _listed(page) == set(FICTION + NONFICTION)


def test_books_invalid_date_is_ignored(client: flask.testing.FlaskClient) -> None:
    page = _books(client, addedSince="not-a-date")
    assert _listed(page) == set(FICTION + NONFICTION)


def test_filters_combine_with_folder(client: flask.testing.FlaskClient) -> None:
    page = _books(client, folder="audiobooks/Fiction", author="alcott")

    # Breadcrumbs keep the author filter
    crumb = re.search(r'class="breadcrumb" href="([^"]*)"', page)
    assert crumb is not None
    assert "author=alcott" in html.unescape(crumb.group(1))

    # The browse drawer keeps the folder and shows the author
    assert _checked(page, "folder") == {"audiobooks/Fiction"}
    assert re.search(r'name="author"\s+value="alcott"', page)


def test_folder_counts_respect_other_filters(
    client: flask.testing.FlaskClient,
) -> None:
    # Without other filters, the folder tree has Fiction (5) and Nonfiction (3)
    page = _books(client, author="e")
    expected_fiction = len(
        _listed(_books(client, author="e", folder="audiobooks/Fiction"))
    )
    assert _folder_counts(page)["Fiction"] == expected_fiction

    # The counts ignore the selected folders, since the tree is used to
    # change them
    page = _books(client, author="e", notFolder="audiobooks/Fiction")
    assert _folder_counts(page)["Fiction"] == expected_fiction

    # Every Alcott book is in Fiction, so the tree collapses to its contents
    assert "Fiction" not in _folder_counts(_books(client, author="alcott"))


def test_books_multiple_folders(client: flask.testing.FlaskClient) -> None:
    page = _books(client, folder=["audiobooks/Fiction", "audiobooks/Nonfiction"])
    assert _listed(page) == set(FICTION + NONFICTION)

    # There are only breadcrumbs for a single folder
    assert 'class="breadcrumb' not in page
    assert _checked(page, "folder") == {"audiobooks/Fiction", "audiobooks/Nonfiction"}


def test_books_excluded_folder(client: flask.testing.FlaskClient) -> None:
    page = _books(client, notFolder="audiobooks/Fiction")
    assert _listed(page) == set(NONFICTION)
    assert _checked(page, "notFolder") == {"audiobooks/Fiction"}

    # Pagination keeps the exclusion
    page = _books(client, notFolder="audiobooks/Fiction", perPage="1")
    assert re.search(
        r'class="nav_link" href="[^"]*notFolder=audiobooks%2FFiction', page
    )


def test_books_excluded_tag(client: flask.testing.FlaskClient) -> None:
    by_tag = _titles_by_tag()
    tag, titles = max(by_tag.items(), key=lambda kv: len(kv[1]))

    page = _books(client, notTag=tag, perPage="100")
    assert _listed(page) == set(FICTION + NONFICTION) - titles
    assert _checked(page, "notTag") == {tag}


def test_books_multiple_tags(client: flask.testing.FlaskClient) -> None:
    by_tag = _titles_by_tag()
    (tag_a, titles_a), (tag_b, titles_b) = sorted(by_tag.items())[:2]

    page = _books(client, tag=[tag_a, tag_b], perPage="100")
    assert _listed(page) == titles_a | titles_b

    page = _books(client, tag=[tag_a, tag_b], tagMatch="all", perPage="100")
    assert _listed(page) == titles_a & titles_b


def test_browse_drawer_folders(client: flask.testing.FlaskClient) -> None:
    page = _books(
        client, folder="audiobooks/Fiction", notFolder="audiobooks/Nonfiction"
    )

    # Every folder can be included or excluded, with the selections checked
    assert _checkboxes(page, "folder") == [
        "audiobooks/Fiction",
        "audiobooks/Nonfiction",
    ]
    assert _checkboxes(page, "notFolder") == _checkboxes(page, "folder")
    assert _checked(page, "folder") == {"audiobooks/Fiction"}
    assert _checked(page, "notFolder") == {"audiobooks/Nonfiction"}


def test_browse_drawer_tags(client: flask.testing.FlaskClient) -> None:
    by_tag = _titles_by_tag()
    least_common = min(sorted(by_tag), key=lambda tag: len(by_tag[tag]))

    page = _books(client, notTag=least_common)
    assert _checked(page, "notTag") == {least_common}
    assert _checked(page, "tag") == set()

    # Selected tags are listed first, followed by the rest
    tags = _checkboxes(page, "tag")
    assert tags[0] == least_common
    assert set(tags) == set(by_tag)

    # Any is the default for tagMatch, and is submitted as an empty value
    assert '<input type="radio" name="tagMatch" value="" checked>' in page
    page = _books(client, tag=least_common, tagMatch="all")
    assert '<input type="radio" name="tagMatch" value="all" checked>' in page


@pytest.mark.parametrize(
    "query, expected",
    [
        ("tag=&author=&orderBy=title", "/books?orderBy=title"),
        ("tag=a&tag=&tag=b&tagMatch=", "/books?tag=a&tag=b"),
        ("author=", "/books"),
    ],
)
def test_books_empty_params_redirect(
    client: flask.testing.FlaskClient, query: str, expected: str
) -> None:
    response = client.get("/books?" + query)
    assert response.status_code == 302
    assert response.headers["Location"] == expected


def test_books_no_redirect_without_empty_params(
    client: flask.testing.FlaskClient,
) -> None:
    assert client.get("/books?tag=a&orderBy=title").status_code == 200


def _form(page: str, form_id: str) -> str:
    match = re.search(rf'<form [^>]*id="{form_id}"[^>]*>(.*?)</form>', page, re.DOTALL)
    assert match is not None
    return match.group(1)


def _hidden(form: str) -> list[tuple[str, str]]:
    return [
        (name, html.unescape(value))
        for name, value in re.findall(
            r'<input type="hidden" name="([^"]*)" value="([^"]*)">', form
        )
    ]


def test_sort_menu_keeps_filters(client: flask.testing.FlaskClient) -> None:
    page = _books(
        client,
        folder=["audiobooks/Fiction", "audiobooks/Nonfiction"],
        notTag="horror",
        author="e",
        orderBy="title",
    )
    sort_menu = _form(page, "sort-menu")
    assert _hidden(sort_menu) == [
        ("folder", "audiobooks/Fiction"),
        ("folder", "audiobooks/Nonfiction"),
        ("notTag", "horror"),
        ("author", "e"),
    ]
    assert '<option value="title" selected>' in sort_menu


def test_browse_drawer_keeps_sort(client: flask.testing.FlaskClient) -> None:
    page = _books(client, orderBy="title", sortAscending="False", perPage="10")
    assert _hidden(_form(page, "browse-drawer")) == [
        ("orderBy", "title"),
        ("sortAscending", "False"),
        ("perPage", "10"),
    ]


def test_menu_button_shows_filter_count(client: flask.testing.FlaskClient) -> None:
    assert 'class="filter_count"' not in _books(client)
    page = _books(client, folder="audiobooks/Fiction", notTag=["a", "b"])
    assert '<span class="filter_count">3</span>' in page


@pytest.mark.parametrize(
    "per_page, has_navigation",
    [
        ("1", True),
        # Everything fits on one page, so there's nowhere to navigate to
        ("100", False),
    ],
)
def test_page_navigation(
    client: flask.testing.FlaskClient, per_page: str, has_navigation: bool
) -> None:
    page = _books(client, perPage=per_page)
    assert ('class="navbar"' in page) is has_navigation


def test_no_page_navigation_without_results(
    client: flask.testing.FlaskClient,
) -> None:
    assert 'class="navbar"' not in _books(client, folder="Nonexistent")


def _nav_items(page: str) -> list[str]:
    """The items in the first page navigation bar: page numbers or "…"."""
    match = re.search(r'<span class="nav_links">(.*?)</span>\n', page, re.S)
    assert match is not None
    return re.sub(r"<[^>]*>", " ", match.group(1)).split()


@pytest.mark.parametrize(
    "current, expected",
    [
        # Pages 3 and 4 are replaced by an ellipsis
        ("0", ["0", "1", "2", "…", "5", "6", "7"]),
        ("7", ["0", "1", "2", "…", "5", "6", "7"]),
        # Every page is near the current page or an end
        ("4", ["0", "1", "2", "3", "4", "5", "6", "7"]),
    ],
)
def test_page_navigation_ellipsis(
    client: flask.testing.FlaskClient, current: str, expected: Sequence[str]
) -> None:
    page = _books(client, perPage="1", page=current)
    assert _nav_items(page) == expected
    # The ellipsis isn't a link, and isn't marked as the current page either
    assert ('class="nav_gap" aria-hidden="true">…</span>' in page) is ("…" in expected)
    assert not re.search(rf'class="nav_link"[^>]*page={current}\D', page)


def _page_jump(page: str) -> str:
    forms = re.findall(
        r'<form class="page_jump" [^>]*action="/books" popover>(.*?)</form>',
        page,
        re.S,
    )
    # The menu is only shown above the list, not repeated below it
    assert len(forms) == 1
    return forms[0]


def _page_options(form: str) -> list[tuple[str, bool, str]]:
    """The (value, selected, label) of each page in the page jump menu.

    Labels are written as e.g. "1. Ab → Cd".
    """
    return [
        (
            value,
            bool(current),
            html.unescape(f"{number}. {start}" + (f" → {end}" if end else "")),
        )
        for value, current, number, start, end in re.findall(
            r'<button name="page" value="(\d+)"( aria-current="page")?>'
            r"<b>(\d+)</b><span>([^<]*)(?:<i>([^<]*)</i>)?</span></button>",
            form,
        )
    ]


def test_page_jump_lists_every_page(client: flask.testing.FlaskClient) -> None:
    page = _books(client, orderBy="title", perPage="2", page="1")
    form = _page_jump(page)
    assert _page_options(form) == [
        ("0", False, "0. Co → Dr"),
        ("1", True, "1. Fr → Ho"),
        ("2", False, "2. Little M → Little W"),
        ("3", False, "3. The I → The W"),
    ]
    # Each page is its own button, so the menu needs no JavaScript
    assert form.count('name="page"') == len(_page_options(form))

    # The menu's button shows the current page's range
    assert '<span>Fr<i>Ho</i></span><svg class="icon">' in page


def test_page_jump_keeps_filters(client: flask.testing.FlaskClient) -> None:
    filters = {"folder": "audiobooks/Fiction", "notTag": "horror"}
    num_books = len(_listed(_books(client, **filters, perPage="100")))
    page = _books(client, **filters, orderBy="title", perPage="1")
    form = _page_jump(page)
    assert _hidden(form) == [
        ("folder", "audiobooks/Fiction"),
        ("notTag", "horror"),
        ("orderBy", "title"),
        ("sortAscending", "True"),
        ("perPage", "1"),
    ]
    options = _page_options(form)
    assert len(options) == num_books
    assert [selected for _, selected, _ in options].count(True) == 1
    assert options[0][1]


@pytest.mark.parametrize("order_by", ["date_added", "last_modified"])
def test_page_jump_dates(client: flask.testing.FlaskClient, order_by: str) -> None:
    options = _page_options(_page_jump(_books(client, orderBy=order_by, perPage="3")))
    assert len(options) == 3
    for index, (value, _, label) in enumerate(options):
        assert value == str(index)
        assert re.fullmatch(
            rf"{index}\. (\d+ )?([A-Z][a-z]{{2}} )?\d+( → \d+ [A-Z][a-z]{{2}} \d{{4}})?",
            label,
        )


def test_page_jump_authors(client: flask.testing.FlaskClient) -> None:
    options = _page_options(_page_jump(_books(client, orderBy="author", perPage="4")))
    assert len(options) == 2
    assert all(re.fullmatch(r"\d\. \S.* → \S.*", label) for _, _, label in options)


def test_no_page_jump_on_single_page(client: flask.testing.FlaskClient) -> None:
    assert 'class="page_jump"' not in _books(client, perPage="100")


def _no_results(page: str) -> str | None:
    """The contents of the message shown when there are no books, if any."""
    match = re.search(r'<p class="no_results">(.*?)</p>', page, re.S)
    return match.group(1) if match is not None else None


def test_no_results_message(client: flask.testing.FlaskClient) -> None:
    message = _no_results(_books(client, folder="Nonexistent"))
    assert message is not None
    assert message.strip()


def test_no_results_message_hidden_with_results(
    client: flask.testing.FlaskClient,
) -> None:
    assert _no_results(_books(client)) is None


def test_no_results_clear_filters_link(client: flask.testing.FlaskClient) -> None:
    message = _no_results(_books(client, folder="Nonexistent", orderBy="title"))
    assert message is not None

    # The link clears the filters, but keeps the sort order
    link = re.search(r'<a href="([^"]*)">', message)
    assert link is not None
    assert "folder" not in html.unescape(link.group(1))
    assert "orderBy=title" in html.unescape(link.group(1))


def test_no_results_title(client: flask.testing.FlaskClient) -> None:
    assert "Page 0 of 0</title>" in _books(client, folder="Nonexistent")


def test_library_root_has_no_breadcrumbs(client: flask.testing.FlaskClient) -> None:
    # Every book is in audiobooks/, so selecting it is the same as selecting
    # everything
    assert 'class="breadcrumb' not in _books(client, folder="audiobooks")


def test_extra_folders_relative_to_library_root(
    client: flask.testing.FlaskClient,
) -> None:
    # Every Alcott book is in Fiction, so the tree collapses past it and it's
    # listed separately
    page = _books(client, folder="audiobooks/Fiction", author="alcott")
    assert _checked(page, "folder") == {"audiobooks/Fiction"}
    assert '<span class="row_name">Fiction</span>' in page


def _qr_popovers(page: str) -> dict[str, str]:
    """The QR code popovers on a page, mapped to the image each one shows."""
    return {
        popover_id: html.unescape(src)
        for popover_id, src in re.findall(
            r'<div class="modal-window" id="([^"]*)" popover><img src="([^"]*)"',
            page,
        )
    }


def test_qr_codes_are_popovers(client: flask.testing.FlaskClient) -> None:
    # The QR codes are popovers, which the browser closes when clicking outside
    # of them or pressing Escape, and toggles from the button that opens them.
    page = _books(client)
    popovers = _qr_popovers(page)
    targets = re.findall(r'<button type="button" [^>]*popovertarget="(qr-[^"]*)"', page)

    # At least the default feed and the single-file feed for every book
    assert len(targets) >= 2 * len(FICTION + NONFICTION)
    assert sorted(targets) == sorted(popovers)
    assert all(popovers.values())

    # Each feed has its own QR code
    assert len(set(popovers.values())) == len(popovers)


def _entries(page: str) -> dict[str, str]:
    """The markup of each book on a page, by title."""
    return {
        html.unescape(title): entry
        for entry in re.findall(r'<article class="entry_row".*?</article>', page, re.S)
        for title in re.findall(r'<span class="book_title">([^<]*)</span>', entry)
    }


def test_covers(
    client: flask.testing.FlaskClient, testgen_config: pathlib.Path
) -> None:
    entries = _entries(_books(client))
    assert entries.keys() == set(FICTION + NONFICTION)

    static_path = testgen_config / "static"
    database = dh.get_database()
    shown_sizes = {}
    for title, entry in entries.items():
        entry_id = re.search(r'data-id="(\d+)"', entry)
        assert entry_id is not None
        cover_images = database["entries"][int(entry_id.group(1))].cover_images
        src = re.search(r'<img src="([^"]*)" class="cover_img"', entry)

        if not cover_images:
            # Books without a cover get one with their title on it
            assert src is None
            assert (
                f'class="cover_img cover_blank" aria-hidden="true">'
                f"<span>{html.escape(title)}</span>"
            ) in entry
            continue

        # The list shows the cover or its thumbnail, whichever is smaller
        assert src is not None
        shown = static_path / unquote(src.group(1).split("/static/", 1)[1])
        cover = static_path / cover_images[0]
        thumbnail = (
            static_path / f"images/entry_cover_cache/{entry_id.group(1)}-thumb.jpg"
        )
        assert shown in (cover, thumbnail)
        assert shown.stat().st_size == min(
            cover.stat().st_size, thumbnail.stat().st_size
        )
        shown_sizes[shown] = shown.stat().st_size

    # The test books include ones without covers, and ones where the cover
    # and the thumbnail are each the smaller one
    assert 0 < len(shown_sizes) < len(entries)
    assert any(path.name.endswith("-thumb.jpg") for path in shown_sizes)
    assert not all(path.name.endswith("-thumb.jpg") for path in shown_sizes)


def test_book_details(client: flask.testing.FlaskClient) -> None:
    entry = _entries(_books(client))["Little Men"]
    assert '<span class="book_author">Louisa May Alcott</span>' in entry
    assert '<li class="series_data">Little Women, book 2</li>' in entry


def test_minimal_javascript(client: flask.testing.FlaskClient) -> None:
    # Everything but keeping the include and exclude toggles for a folder or
    # tag exclusive of each other works without JavaScript.
    page = _books(client)
    assert page.count("<script") == 1
    assert not re.search(r"\son[a-z]+=|javascript:", page)


def _stylesheets(page: str) -> list[str]:
    return re.findall(r'<link rel="stylesheet" href="([^"]*)">', page)


def _theme_options(page: str) -> dict[str, str]:
    select = re.search(
        r'<select id="theme-select" name="theme" form="theme-form">(.*?)</select>',
        page,
        re.S,
    )
    assert select is not None
    return dict(
        re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', select.group(1))
    )


def test_theme_choices(client: flask.testing.FlaskClient) -> None:
    assert _theme_options(_books(client)) == {
        "default": "Classic",
        "card_catalog": "Card catalog",
        "plain": "Plain",
        "shelf": "Shelf",
        "tape_deck": "Tape deck",
    }


@pytest.mark.parametrize("theme", ["card_catalog", "plain", "shelf", "tape_deck"])
def test_choose_theme(
    client: flask.testing.FlaskClient, testgen_config: pathlib.Path, theme: str
) -> None:
    default_stylesheets = _stylesheets(_books(client))

    # Choosing a theme keeps the rest of the URL, but drops the theme, which is
    # stored in a cookie
    response = client.get(f"/books?theme={theme}&orderBy=title")
    assert response.status_code == 302
    assert response.location == "/books?orderBy=title"

    page = _books(client)
    *stylesheets, theme_stylesheet = _stylesheets(page)
    assert stylesheets == default_stylesheets
    assert theme_stylesheet.endswith(f"/css/themes/{theme}.css")
    assert (testgen_config / f"static/css/themes/{theme}.css").exists()
    assert f'<option value="{theme}" selected>' in page


def test_choose_default_theme(client: flask.testing.FlaskClient) -> None:
    default_stylesheets = _stylesheets(_books(client))
    client.get("/books?theme=plain")
    assert _stylesheets(_books(client)) != default_stylesheets

    client.get("/books?theme=default")
    page = _books(client)
    assert _stylesheets(page) == default_stylesheets
    assert '<option value="default" selected>' in page


@pytest.mark.parametrize("theme", ["", "nonexistent", "../main"])
def test_unknown_theme_is_ignored(
    client: flask.testing.FlaskClient, theme: str
) -> None:
    default_stylesheets = _stylesheets(_books(client))
    client.set_cookie("theme", theme)
    assert _stylesheets(_books(client)) == default_stylesheets


def test_custom_theme(
    client: flask.testing.FlaskClient, testgen_config: pathlib.Path
) -> None:
    # Themes added to the themes directory can be chosen like the built-in ones
    themes_dir = testgen_config / "static/css/themes"
    themes_dir.mkdir(parents=True, exist_ok=True)
    (themes_dir / "my_own_theme.css").write_text(":root { --accent: hotpink; }")

    assert _theme_options(_books(client))["my_own_theme"] == "My own theme"
    client.get("/books?theme=my_own_theme")
    assert _stylesheets(_books(client))[-1].endswith("/css/themes/my_own_theme.css")


def _scheme_radios(page: str) -> dict[str, bool]:
    """The colour scheme choices in the menu, and whether each is checked."""
    parser = _InputParser()
    parser.feed(page)
    return {
        attrs["value"] or "": "checked" in attrs
        for attrs in parser.inputs
        if attrs.get("type") == "radio" and attrs.get("name") == "scheme"
    }


def _html_scheme(page: str) -> str | None:
    """The colour scheme forced on the page, if any."""
    match = re.search(r'<html lang="en"(?: data-scheme="([^"]*)")?>', page)
    assert match is not None
    return match.group(1)


def _assert_scheme(page: str, scheme: str | None) -> None:
    """Check that the page is in ``scheme``, or follows the system for None."""
    assert _html_scheme(page) == scheme
    color_scheme = scheme or "light dark"
    assert f'<meta name="color-scheme" content="{color_scheme}">' in page
    checked = [
        value for value, is_checked in _scheme_radios(page).items() if is_checked
    ]
    assert checked == [scheme or "system"]


def test_scheme_follows_system_by_default(client: flask.testing.FlaskClient) -> None:
    page = _books(client)
    assert list(_scheme_radios(page)) == ["light", "dark", "system"]
    _assert_scheme(page, None)


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_choose_scheme(client: flask.testing.FlaskClient, scheme: str) -> None:
    # Choosing a colour scheme keeps the rest of the URL, but drops the
    # scheme, which is stored in a cookie
    response = client.get(f"/books?scheme={scheme}&orderBy=title")
    assert response.status_code == 302
    assert response.location == "/books?orderBy=title"

    cookie = client.get_cookie("scheme")
    assert cookie is not None
    assert cookie.value == scheme
    _assert_scheme(_books(client), scheme)


def test_choose_system_scheme(client: flask.testing.FlaskClient) -> None:
    client.get("/books?scheme=dark")
    _assert_scheme(_books(client), "dark")

    client.get("/books?scheme=system")
    assert client.get_cookie("scheme") is None
    _assert_scheme(_books(client), None)


@pytest.mark.parametrize("scheme", ["", "purple", "Dark", "default"])
def test_unknown_scheme_is_ignored(
    client: flask.testing.FlaskClient, scheme: str
) -> None:
    client.get("/books?scheme=dark")
    response = client.get("/books?" + urlencode({"scheme": scheme}))
    assert response.status_code == 302
    assert response.location == "/books"
    _assert_scheme(_books(client), "dark")


@pytest.mark.parametrize("scheme", ["", "purple", "system"])
def test_unknown_scheme_cookie_is_ignored(
    client: flask.testing.FlaskClient, scheme: str
) -> None:
    client.set_cookie("scheme", scheme)
    _assert_scheme(_books(client), None)


def test_choose_theme_and_scheme(client: flask.testing.FlaskClient) -> None:
    # The theme and the colour scheme are chosen with the same form
    response = client.get("/books?theme=shelf&scheme=dark&orderBy=title")
    assert response.status_code == 302
    assert response.location == "/books?orderBy=title"

    page = _books(client)
    assert _stylesheets(page)[-1].endswith("/css/themes/shelf.css")
    _assert_scheme(page, "dark")


@pytest.mark.parametrize(
    "theme, has_schemes",
    [
        ("default", True),
        ("shelf", True),
        ("plain", True),
        ("card_catalog", False),
        ("tape_deck", False),
    ],
)
def test_scheme_toggle_only_for_themes_with_schemes(
    client: flask.testing.FlaskClient, theme: str, has_schemes: bool
) -> None:
    client.get("/books?scheme=dark")
    client.get(f"/books?theme={theme}")
    page = _books(client)
    if has_schemes:
        _assert_scheme(page, "dark")
    else:
        # A theme with only one colour scheme has no choice to offer, and
        # isn't forced into the other one
        assert _scheme_radios(page) == {}
        assert _html_scheme(page) is None
        assert '<meta name="color-scheme" content="light dark">' in page

    # The chosen scheme is kept for when the theme changes back
    client.get("/books?theme=default")
    _assert_scheme(_books(client), "dark")


@pytest.mark.parametrize(
    "css, has_schemes",
    [
        (":root { color-scheme: light dark; --accent: hotpink; }", True),
        (":root {\n    color-scheme:dark   light;\n}", True),
        (":root { --accent: hotpink; }", False),
        (":root { color-scheme: light; }", False),
        (":root { color-scheme: dark; }", False),
        ("/* color-scheme: light dark */ :root { color-scheme: dark; }", False),
    ],
)
def test_custom_theme_schemes(
    client: flask.testing.FlaskClient,
    testgen_config: pathlib.Path,
    css: str,
    has_schemes: bool,
) -> None:
    # A theme offers the choice of colour scheme by saying that it has both
    themes_dir = testgen_config / "static/css/themes"
    themes_dir.mkdir(parents=True, exist_ok=True)
    (themes_dir / "my_own_theme.css").write_text(css)

    client.get("/books?theme=my_own_theme&scheme=light")
    page = _books(client)
    assert bool(_scheme_radios(page)) == has_schemes
    assert _html_scheme(page) == ("light" if has_schemes else None)


def test_appearance_is_at_top_of_menu(client: flask.testing.FlaskClient) -> None:
    page = _books(client, folder="audiobooks/Fiction")
    drawer = _form(page, "browse-drawer")
    header = drawer.index('<div class="drawer_header">')
    theme_select = drawer.index(
        '<select id="theme-select" name="theme" form="theme-form">'
    )
    assert header < theme_select < drawer.index("<summary>Folders</summary>")

    # The theme and colour scheme (the select, three radio buttons and the
    # button) are submitted with the theme form rather than with the filters,
    # which the theme form keeps
    appearance = drawer[theme_select : drawer.index('<div class="browse_heading">')]
    assert appearance.count('form="theme-form"') == 5
    assert '<button type="submit" form="theme-form">Use</button>' in appearance
    assert ("folder", "audiobooks/Fiction") in _hidden(_form(page, "theme-form"))


def test_stale_stylesheets_are_not_used(
    client: flask.testing.FlaskClient, testgen_config: pathlib.Path
) -> None:
    # Stylesheets left over from older versions aren't included in the page
    css_dir = testgen_config / "static/css"
    css_dir.mkdir(parents=True, exist_ok=True)
    (css_dir / "fontawesome-subset.css").write_text(".fa { color: red; }")

    stylesheets = _stylesheets(_books(client))
    assert stylesheets
    assert not any("fontawesome" in stylesheet for stylesheet in stylesheets)


def _wordmark(page: str) -> str:
    match = re.search(r'<a class="wordmark" href="/books">(.*?)</a>', page)
    assert match is not None
    return match.group(1)


@pytest.mark.parametrize(
    "site_logo, expected_logo",
    [
        # audio-feeder's own logo
        (None, '<svg class="icon logo" aria-hidden="true"><use href="#i-logo"/></svg>'),
        # No logo
        ("", ""),
        # Paths are relative to the static directory, and URLs are used as-is
        (
            "images/logo.png",
            '<img class="logo" src="http://localhost:80/static/images/logo.png" alt="">',
        ),
        (
            "https://example.com/logo.svg",
            '<img class="logo" src="https://example.com/logo.svg" alt="">',
        ),
    ],
)
def test_site_title_and_logo(
    client: flask.testing.FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
    site_logo: str | None,
    expected_logo: str,
) -> None:
    settings = {"site_title": "Our <Audiobooks>", "site_logo": site_logo}
    read_from_config = pages.read_from_config
    monkeypatch.setattr(
        pages,
        "read_from_config",
        lambda field: settings[field] if field in settings else read_from_config(field),
    )

    page = _books(client)
    assert _wordmark(page) == f"{expected_logo}<span>Our &lt;Audiobooks&gt;</span>"

    # The logo is also the favicon
    favicons = re.findall(r'<link rel="icon"[^>]* href="([^"]*)">', page)
    if site_logo is None:
        assert len(favicons) == 1
        assert favicons[0].startswith("data:image/svg+xml,")
    elif site_logo:
        assert favicons == [re.search(r'src="([^"]*)"', expected_logo).group(1)]
    else:
        assert favicons == []


def test_default_site_title(client: flask.testing.FlaskClient) -> None:
    assert _wordmark(_books(client)).endswith("<span>audio-feeder</span>")


def _feed_channel(client: flask.testing.FlaskClient, title: str) -> ET.Element:
    """The ``<channel>`` of the RSS feed of the book with this title."""
    database = dh.get_database()
    (entry_id,) = (
        entry_id
        for entry_id, entry in database["entries"].items()
        if dh.get_data_obj(entry, database).title == title
    )
    response = client.get(f"/rss/{entry_id}.xml")
    assert response.status_code == 200
    channel = ET.fromstring(response.get_data()).find("channel")
    assert channel is not None
    return channel


def test_rss_feed_title_and_description(
    client: flask.testing.FlaskClient, testgen_config: pathlib.Path
) -> None:
    # The test configuration has a copy of every template, but an installed
    # server normally doesn't, and uses the ones in the package
    shutil.rmtree(testgen_config / "templates")

    channel = _feed_channel(client, "The Invisible Man")

    # The feed uses the RSS templates rather than the book list's, so the
    # title is plain text
    assert channel.findtext("title") == "H G Wells - The Invisible Man"

    # ...and the description has the book's details as well as its
    # description
    description = channel.findtext("description")
    assert description is not None
    assert "ISBN" in description
    assert "1605206288" in description
    assert "least actually read" in description
