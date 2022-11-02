"""Types common between database_handler and sql_database_handler.

This exists for compatibility while the old database_handler code still exists.
"""
import typing

from . import object_handler as oh
from ._object_types import SchemaObject
from ._useful_types import PathType

ID = typing.NewType("ID", int)
TableName = typing.NewType("TableName", str)
Table = typing.Mapping[ID, SchemaObject]
MutableTable = typing.MutableMapping[ID, SchemaObject]
Database = typing.Mapping[TableName, Table]
MutableDatabase = typing.MutableMapping[TableName, MutableTable]


class DatabaseHandler(typing.Protocol):
    def __init__(self, db_loc: PathType):
        ...

    def save_table(self, table_name: TableName, table_contents: Table) -> None:
        ...

    def load_table(self, table_name: TableName) -> Table:
        ...

    def save_database(self, database: Database) -> None:
        ...

    def load_database(self) -> Database:
        ...
