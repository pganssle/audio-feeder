"""Tests for audio_feeder.pages"""

import datetime
import html
import pathlib
import re
import threading
from collections.abc import Iterator, Mapping, Sequence
from urllib.parse import urlencode

import flask.testing
import pytest

from audio_feeder import app as af_app
from audio_feeder import database_handler as dh
from audio_feeder import pages, updater

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


def _checked(page: str, name: str) -> set[str]:
    """The values of the checked checkboxes named ``name``."""
    return {
        html.unescape(value)
        for value in re.findall(
            rf'<input type="checkbox" name="{name}" value="([^"]*)" checked>', page
        )
    }


def _checkboxes(page: str, name: str) -> list[str]:
    """The values of all the checkboxes named ``name``, in order."""
    return [
        html.unescape(value)
        for value in re.findall(
            rf'<input type="checkbox" name="{name}" value="([^"]*)"', page
        )
    ]


def test_books_unfiltered(client: flask.testing.FlaskClient) -> None:
    page = _books(client)
    assert _listed(page) == set(FICTION + NONFICTION)

    # Every book is below audiobooks/, so the top level offers its subfolders
    assert 'Fiction <span class="subfolder_count">(5)</span>' in page
    assert 'Nonfiction <span class="subfolder_count">(3)</span>' in page


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
    assert ">audiobooks</a>" in page

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

    assert "Author: ALCOTT" in page


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

    # Removing the author filter keeps the folder
    remove_link = re.search(r'class="remove_filter" href="([^"]*)"', page)
    assert remove_link is not None
    remove_url = html.unescape(remove_link.group(1))
    assert "folder=audiobooks%2FFiction" in remove_url
    assert "author" not in remove_url

    # The browse drawer keeps the folder and shows the author
    assert _checked(page, "folder") == {"audiobooks/Fiction"}
    assert re.search(r'name="author"\s+value="alcott"', page)


def test_folder_counts_respect_other_filters(
    client: flask.testing.FlaskClient,
) -> None:
    # Without other filters, the top level offers Fiction (5) and Nonfiction (3)
    page = _books(client, author="e")
    counts = dict(
        re.findall(r'>([^<>]+) <span class="subfolder_count">\((\d+)\)', page)
    )
    expected_fiction = len(
        {"Dracula", "The Invisible Man", "Little Women", "Little Men", "Frankenstein"}
        & _listed(_books(client, author="e", folder="audiobooks/Fiction"))
    )
    assert counts.get("Fiction") == str(expected_fiction)
    # Every Alcott book is in Fiction, so there's nothing to navigate into
    assert 'class="subfolder"' not in _books(client, author="alcott")


def test_books_multiple_folders(client: flask.testing.FlaskClient) -> None:
    page = _books(client, folder=["audiobooks/Fiction", "audiobooks/Nonfiction"])
    assert _listed(page) == set(FICTION + NONFICTION)

    # With more than one folder, each is shown as a removable filter rather
    # than with breadcrumbs
    assert 'class="breadcrumb' not in page
    assert "Folder: audiobooks/Fiction" in page
    assert "Folder: audiobooks/Nonfiction" in page


def test_books_excluded_folder(client: flask.testing.FlaskClient) -> None:
    page = _books(client, notFolder="audiobooks/Fiction")
    assert _listed(page) == set(NONFICTION)
    assert "Not in folder: audiobooks/Fiction" in page

    # The folder navigation doesn't offer the excluded folder
    assert 'Fiction <span class="subfolder_count">' not in page

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
    assert f"Not tag: {html.escape(tag)}" in page


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
