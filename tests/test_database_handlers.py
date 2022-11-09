import os
import pathlib
import shutil
import typing

import pytest

from audio_feeder import _db_types
from audio_feeder import object_handler as oh
from audio_feeder import sql_database_handler as sdh
from audio_feeder import yaml_database_handler as ydh


@pytest.fixture(
    params=[
        (pathlib.Path(__file__).parent / "data/db.sqlite", sdh.SqlDatabaseHandler),
        (pathlib.Path(__file__).parent / "data/yaml_db", ydh.YamlDatabaseHandler),
    ]
)
def db_handler(
    request, tmp_path: pathlib.Path
) -> typing.Iterator[_db_types.DatabaseHandler]:
    db_loc, handler_type = request.param
    copy_loc = tmp_path / db_loc.name

    if db_loc.is_dir():
        shutil.copytree(db_loc, copy_loc)
    else:
        shutil.copy(db_loc, copy_loc)

    yield handler_type(copy_loc)


def test_load_db(db_handler: _db_types.DatabaseHandler) -> None:
    db_tables = db_handler.load_database()

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


def test_load_empty_sql_database(tmp_path: pathlib.Path) -> None:
    """Test that the SQL database handler can load an empty database.

    This is the one point of difference between YAML and SQL database handlers;
    the YAML database throws an error but SQL initializes the database for us.
    The reason it is different is that the capability is not built in to the
    YAML handler, and the YAML database is going to be deprecated, so this is
    a YAGNI situation.
    """
    db = tmp_path / "db.sqlite"
    handler = sdh.SqlDatabaseHandler(db)

    db_tables = handler.load_database()
    for table_name, table in db_tables.items():
        assert len(table) == 0


def test_load_empty_yaml_database(tmp_path: pathlib.Path) -> None:
    """Test that the YAML database fails when loading a missing database.

    This is the one point of difference between YAML and SQL database handlers;
    the YAML database throws an error but SQL initializes the database for us.
    The reason it is different is that the capability is not built in to the
    YAML handler, and the YAML database is going to be deprecated, so this is
    a YAGNI situation.
    """
    db = tmp_path / "db/"
    handler = ydh.YamlDatabaseHandler(db)

    with pytest.raises(ValueError):
        handler.load_database()


def test_load_table(db_handler: _db_types.DatabaseHandler) -> None:
    books = db_handler.load_table("books")

    assert len(books) == 5
    for book in books.values():
        assert isinstance(book, oh.Book)


def test_save_database(db_handler: _db_types.DatabaseHandler) -> None:
    db_tables = db_handler.load_database()

    db_tables["books"][21144] = oh.Book(
        id=21144,
        title="The House of Mirth",
        authors=["Edith Wharton"],
        author_ids=[496925],
    )

    db_handler.save_database(db_tables)

    db_tables_reload = db_handler.load_database()

    assert db_tables is not db_tables_reload

    assert 21144 in db_tables["books"]


def test_save_table(db_handler: _db_types.DatabaseHandler) -> None:
    db_tables = db_handler.load_database()

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
    db_handler.save_table("authors", db_tables["authors"])

    db_tables_reload = db_handler.load_database()
    assert 2444 in db_tables_reload["authors"]
    assert 11243 not in db_tables_reload["books"]


def test_save_database_remove(db_handler: _db_types.DatabaseHandler) -> None:
    db_tables = db_handler.load_database()

    book_ids = [book_id for book_id in db_tables["books"].keys()]
    for book_id in book_ids[:3]:
        del db_tables["books"][book_id]

    db_handler.save_table("books", db_tables["books"])

    books_table = db_handler.load_table("books")

    assert books_table is not db_tables["books"]

    for book_id in book_ids[:3]:
        assert book_id not in books_table

    for book_id in book_ids[3:]:
        assert book_id in books_table
