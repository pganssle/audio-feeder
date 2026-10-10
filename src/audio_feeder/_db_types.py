"""Types common between database_handler and sql_database_handler.

This exists for compatibility while the old database_handler code still exists.
"""

from collections.abc import Mapping, MutableMapping
from typing import NewType, Protocol

from ._object_types import ID, SchemaObject
from ._useful_types import PathType

TableName = NewType("TableName", str)
Table = Mapping[ID, SchemaObject]
MutableTable = MutableMapping[ID, SchemaObject]
Database = Mapping[TableName, Table]
MutableDatabase = MutableMapping[TableName, MutableTable]


# pragma: nocover
class DatabaseHandler(Protocol):
    def __init__(self, db_loc: PathType): ...

    def save_table(self, table_name: TableName, table_contents: Table) -> None: ...

    def load_table(self, table_name: TableName) -> Table: ...

    def save_database(self, database: Database) -> None: ...

    def load_database(self) -> Database: ...
