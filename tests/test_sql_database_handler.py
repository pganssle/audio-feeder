import os
import pathlib
import shutil
import typing

import pytest

from audio_feeder import object_handler as oh
from audio_feeder import sql_database_handler as sdh


@pytest.fixture
def db(tmp_path) -> typing.Iterator[pathlib.Path]:
    db_loc = pathlib.Path(__file__).parent / "data/db.sqlite"
    copy_loc = tmp_path / "db.sqlite"

    shutil.copyfile(db_loc, copy_loc)

    yield copy_loc


def test_load_db(db: pathlib.Path) -> None:
    handler = sdh.SqlDatabaseHandler(db)

    db_tables = handler.load_database()

    assert len(db_tables["books"]) == 5
    for book in db_tables["books"].values():
        assert isinstance(book, oh.Book)

    assert len(db_tables["entries"]) == 5
    for entry in db_tables["entries"].values():
        assert isinstance(entry, oh.Entry)

        assert entry.type == "Book"
        assert entry.data_id in db_tables["books"]

    # Little Women
    lw_entry = db_tables["entries"][787031]
    assert lw_entry.path == pathlib.Path(
        "audiobooks/Fiction/Louisa May Alcott - [Little Women 01] - Little Women"
    )
    assert os.fspath(lw_entry.cover_images[0]).startswith("media/audiobooks/Fiction")

    twof_entry = db_tables["entries"][712130]
    # Edith Wharton - The Writing of Fiction
    assert twof_entry.path == pathlib.Path(
        "audiobooks/Nonfiction/Edith Wharton - The Writing of Fiction"
    )
    assert os.fspath(twof_entry.cover_images[0]).startswith("images/entry_cover_cache")


def test_load_empty_database(tmp_path):
    db = tmp_path / "db.sqlite"

    handler = sdh.SqlDatabaseHandler(db)

    db_tables = handler.load_database()
    for table_name, table in db_tables.items():
        assert len(table) == 0


def test_load_table(db: pathlib.Path) -> None:
    handler = sdh.SqlDatabaseHandler(db)

    books = handler.load_table("books")

    assert len(books) == 5
    for book in books.values():
        assert isinstance(book, oh.Book)


def test_save_database(db: pathlib.Path) -> None:
    handler = sdh.SqlDatabaseHandler(db)
    db_tables = handler.load_database()

    db_tables["books"][21144] = oh.Book(
        id=21144,
        title="The House of Mirth",
        authors=["Edith Wharton"],
        author_ids=[496925],
    )

    handler.save_database(db_tables)

    db_tables_reload = handler.load_database()

    assert db_tables is not db_tables_reload

    assert 21144 in db_tables["books"]


def test_save_table(db: pathlib.Path) -> None:
    handler = sdh.SqlDatabaseHandler(db)
    db_tables = handler.load_database()

    db_tables["authors"][2444] = oh.Author(
        id=2444,
        name="H.G. Wells",
        sort_name="Wells, H.G.",
        tags=["fiction", "science.fiction"],
        books=[11243],
    )
    db_tables["books"][11243] = oh.Book(
        id=11243,
        title="War of the Worlds",
        authors=["H.G. Wells"],
        author_ids=[2444],
    )
    handler.save_table("authors", db_tables["authors"])

    db_tables_reload = handler.load_database()
    assert 2444 in db_tables_reload["authors"]
    assert 11243 not in db_tables_reload["books"]


def test_save_database_remove(db: pathlib.Path) -> None:
    handler = sdh.SqlDatabaseHandler(db)
    db_tables = handler.load_database()

    book_ids = [book_id for book_id in db_tables["books"].keys()]
    for book_id in book_ids[:3]:
        del db_tables["books"][book_id]

    handler.save_table("books", db_tables["books"])

    books_table = handler.load_table("books")

    assert books_table is not db_tables["books"]

    for book_id in book_ids[:3]:
        assert book_id not in books_table

    for book_id in book_ids[3:]:
        assert book_id in books_table
