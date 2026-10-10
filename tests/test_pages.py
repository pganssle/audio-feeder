"""Tests for audio_feeder.pages"""

import pathlib
import threading
from collections.abc import Iterator, Mapping
from urllib.parse import urlencode

import flask.testing
import pytest

from audio_feeder import app as af_app
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


def _books(client: flask.testing.FlaskClient, **params: str) -> str:
    response = client.get("/books?" + urlencode(params))
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_books_unfiltered(client: flask.testing.FlaskClient) -> None:
    page = _books(client)
    for title in FICTION + NONFICTION:
        assert title in page

    # Every book is below audiobooks/, so the top level offers its subfolders
    assert 'Fiction <span class="subfolder_count">(5)</span>' in page
    assert 'Nonfiction <span class="subfolder_count">(3)</span>' in page


@pytest.mark.parametrize(
    "folder, included, excluded",
    [
        ("audiobooks/Fiction", FICTION, NONFICTION),
        ("audiobooks/Nonfiction", NONFICTION, FICTION),
        ("/audiobooks/Nonfiction/", NONFICTION, FICTION),
        ("audiobooks", FICTION + NONFICTION, ()),
        ("Nonexistent", (), FICTION + NONFICTION),
    ],
)
def test_books_filtered_by_folder(
    client: flask.testing.FlaskClient,
    folder: str,
    included: tuple[str, ...],
    excluded: tuple[str, ...],
) -> None:
    page = _books(client, folder=folder)
    for title in included:
        assert title in page
    for title in excluded:
        assert title not in page


def test_books_folder_navigation(client: flask.testing.FlaskClient) -> None:
    page = _books(client, folder="audiobooks/Fiction", orderBy="title", page="0")

    # Breadcrumbs link back up, and the current folder isn't a link
    assert '<span class="breadcrumb current_folder">Fiction</span>' in page
    assert ">All</a>" in page
    assert ">audiobooks</a>" in page

    # The sort form keeps the folder filter
    assert '<input type="hidden" name="folder" value="audiobooks/Fiction">' in page

    # Folder links keep the sort order
    assert "orderBy=title" in page.split('class="breadcrumb"', 1)[1].split(">", 1)[0]


def test_books_pagination_keeps_folder(client: flask.testing.FlaskClient) -> None:
    page = _books(client, folder="audiobooks/Fiction", perPage="2")

    assert "folder=audiobooks%2FFiction" in page
    # 5 Fiction books at 2 per page is 3 pages
    assert "Page 0 of 2" in page


def test_books_invalid_folder_is_ignored(client: flask.testing.FlaskClient) -> None:
    page = _books(client, folder="../secrets")
    for title in FICTION + NONFICTION:
        assert title in page
