"""Database handler using a set of YAML files as a database"""

import functools
import os
import pathlib
import shutil
import typing

import yaml

from . import file_probe as fp
from . import object_handler as oh
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


def _path_constructor(
    loader: yaml.SafeLoader, node: yaml.nodes.ScalarNode
) -> pathlib.Path:
    """Construct a pathlib.Path"""
    scalar = loader.construct_scalar(node)
    assert isinstance(scalar, str)
    return pathlib.Path(scalar)


def _path_representer(
    dumper: yaml.SafeDumper, path: pathlib.Path
) -> yaml.nodes.ScalarNode:
    return dumper.represent_scalar("!Path", os.fspath(path))


def _file_info_constructor(
    loader: yaml.SafeLoader, node: yaml.nodes.MappingNode
) -> fp.FileInfo:
    mapping = loader.construct_mapping(node)
    return fp.FileInfo.from_json(typing.cast(fp.FFProbeReturnJSON, mapping))


def _file_info_representer(
    dumper: yaml.SafeDumper, file_info: fp.FileInfo
) -> yaml.nodes.MappingNode:
    return dumper.represent_mapping("!FileInfo", file_info.to_json())


@functools.lru_cache(None)
def _loader() -> typing.Type[yaml.SafeLoader]:
    class CustomSafeLoader(yaml.SafeLoader):
        pass

    CustomSafeLoader.add_constructor("!Path", _path_constructor)
    CustomSafeLoader.add_constructor("!FileInfo", _file_info_constructor)

    return CustomSafeLoader


@functools.lru_cache(None)
def _dumper() -> typing.Type[yaml.SafeDumper]:
    class CustomSafeDumper(yaml.SafeDumper):
        pass

    for path_type in [pathlib.Path, pathlib.PosixPath, pathlib.WindowsPath]:
        CustomSafeDumper.add_representer(path_type, _path_representer)

    CustomSafeDumper.add_representer(fp.FileInfo, _file_info_representer)
    return CustomSafeDumper


class YamlDatabaseHandler:
    def __init__(self, db_loc: PathType):
        self._db = pathlib.Path(db_loc)

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
            yaml.dump(table_obj, stream=yf, default_flow_style=False, Dumper=_dumper())

    def load_table(self, table_name: TableName) -> Table:
        """
        Loads a table from the YAML file ``table_loc``.
        """

        type_name = oh.TABLE_MAPPING[table_name]
        table_type = oh.TYPE_MAPPING[type_name]
        table_loc = self._get_table_loc(table_name)
        with open(table_loc, "r") as yf:
            table_file = yaml.load(yf, Loader=_loader())

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
            for table_name in oh.TABLE_MAPPING.keys():
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

        for table_name in oh.TABLE_MAPPING.keys():
            table_loc = self._get_table_loc(table_name)
            if not table_loc.exists():
                tables[table_name] = {}
            else:
                tables[table_name] = typing.cast(
                    MutableTable, self.load_table(table_name)
                )
        return tables
