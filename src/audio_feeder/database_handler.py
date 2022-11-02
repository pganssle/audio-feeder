import functools
import os
import pathlib
import typing

from . import object_handler as oh
from ._db_types import (
    ID,
    Database,
    DatabaseHandler,
    MutableDatabase,
    Table,
    TableName,
)
from ._useful_types import PathType
from .config import read_from_config


@functools.lru_cache(None)
def _get_handler_by_suffix(suffix: str) -> typing.Type[DatabaseHandler]:
    suffix = suffix.lstrip(".")
    if suffix in ("", "yml", "yaml"):
        from .yaml_database_handler import YamlDatabaseHandler

        return YamlDatabaseHandler
    elif suffix in ("sqlite", "sqlite3"):
        from .sql_database_handler import SqlDatabaseHandler

        return SqlDatabaseHandler

    raise ValueError(f"Cannot parse suffix: {suffix}")


@functools.lru_cache
def _get_handler_from_db_loc(db_loc: PathType) -> DatabaseHandler:
    handler_type = _get_handler_by_suffix(pathlib.Path(db_loc).suffix)
    return handler_type(db_loc)


@functools.lru_cache
def _get_handler(db_loc: typing.Optional[PathType]) -> DatabaseHandler:
    db_loc = _get_db_loc(db_loc)
    handler_type = _get_handler_by_suffix(pathlib.Path(db_loc).suffix)
    return handler_type(db_loc)


def load_database(
    db_loc: typing.Optional[PathType] = None,
) -> Database:
    """
    Loads the 'database' into memory.

    For now, the 'database' is a directory full of YAML files, because I
    have not yet implemented the ability to make hand-modifications to the
    metadata, and I don't know how to easily edit SQL databases.
    """
    handler = _get_handler(db_loc)

    return handler.load_database()


def save_database(database: Database, db_loc: typing.Optional[PathType] = None) -> None:
    """
    Saves the 'database' into memory. See :func:`load_database` for details.
    """
    handler = _get_handler(db_loc)
    return handler.save_database(database)


@functools.lru_cache
def _get_default_database_cached() -> Database:
    return load_database()


def get_database(refresh: bool = False) -> Database:
    """
    Loads the current default database into a cached read-only memory
    """
    if refresh:
        _get_default_database_cached.cache_clear()

    return _get_default_database_cached()


def get_database_table(
    table_name: TableName, database: typing.Optional[Database] = None
) -> Table:
    """
    Loads a database table from a cached read-only database.
    """
    db = database or get_database()

    return db[table_name]


def get_data_obj(
    entry_obj, database: typing.Optional[Database] = None
) -> oh.BaseObject:
    """
    Given an :class:`object_handler.Entry` object, return the corresponding data
    object, loaded from the appropriate table.
    """
    # Loads the data table
    table = get_database_table(entry_obj.table, database=database)

    return table[entry_obj.data_id]


def _get_db_loc(db_loc: typing.Optional[PathType] = None) -> PathType:
    if db_loc is None:
        db_loc = read_from_config("database_loc")

    return db_loc
