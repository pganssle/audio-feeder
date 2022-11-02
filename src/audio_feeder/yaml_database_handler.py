"""Database handler using a set of YAML files as a database"""

import functools
import os
import pathlib
import shutil
import typing

import yaml

from . import object_handler as oh
from . import schema_handler
from ._db_types import (
    ID,
    Database,
    MutableDatabase,
    MutableTable,
    Table,
    TableName,
)
from ._useful_types import PathType

DB_VERSION: int = 0


class YamlDatabaseHandler:
    def __init__(self, db_loc: PathType):
        self._db = pathlib.Path(db_loc)

    @functools.cached_property
    def schema(self) -> schema_handler.SchemaDict:
        return schema_handler.load_schema()

    def _get_table_loc(self, table_name: TableName) -> pathlib.Path:
        return self._db / f"{table_name}.yml"

    def _get_bak_loc(self, table_loc: pathlib.Path) -> pathlib.Path:
        return table_loc.with_suffix(f"{table_loc.suffix}.bak")

    def save_table(self, table_name: TableName, table_contents: Table) -> None:
        """
        Saves a table of type ``table_type`` to a YAML file ``table_loc``
        """
        table_list = [obj.to_dict_sparse() for _, obj in table_contents.items()]
        table_obj = {"db_version": DB_VERSION, "data": table_list}

        table_loc = self._get_table_loc(table_name)

        if table_loc.exists():
            # Cache a backup of this
            shutil.copy2(table_loc, self._get_bak_loc(table_loc))

        with open(table_loc, "w") as yf:
            yaml.dump(table_obj, stream=yf, default_flow_style=False)

    def load_table(self, table_name: TableName) -> Table:
        """
        Loads a table from the YAML file ``table_loc``.
        """

        type_name = self.schema["tables"][table_name]
        table_type = oh.TYPE_MAPPING[type_name]
        table_loc = self._get_table_loc(table_name)
        with open(table_loc, "r") as yf:
            table_file = yaml.safe_load(yf)

        assert table_file["db_version"] == DB_VERSION
        table_list = table_file["data"]

        raw_table = (table_type(**params) for params in table_list)
        table_by_id = {ID(x.id): x for x in raw_table}

        return table_by_id

    def save_database(self, database: Database) -> None:
        """
        Saves the 'database'  to disk.
        """
        if not self._db.exists():
            os.makedirs(self._db)

        # Try and do this as a pseudo-atomic operation
        tables_saved = []
        try:
            for table_name, type_name in self.schema["tables"].items():
                self.save_table(table_name, database[table_name])
                tables_saved.append(table_name)
        except Exception as e:
            # Restore the .bak files that were made
            for table_loc in tables_saved:
                bak_loc = self._get_bak_loc(self._get_table_loc(table_loc))
                if bak_loc.exists():
                    shutil.move(bak_loc, table_loc)

            raise e

    def load_database(self) -> Database:
        if not self._db.exists():
            raise ValueError(f"Database not found: {os.fspath(self._db)}")

        tables: MutableDatabase = {}

        for table_name, type_name in self.schema["tables"].items():
            table_type = oh.TYPE_MAPPING[type_name]
            table_loc = self._get_table_loc(table_name)
            if not table_loc.exists():
                tables[table_name] = {}
            else:
                tables[table_name] = typing.cast(
                    MutableTable, self.load_table(table_name)
                )
        return tables
