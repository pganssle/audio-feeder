"""Database handler using a SQL database"""

import datetime
import functools
import os
import pathlib
import sqlite3
import typing
from collections import abc

import attrs
import sqlalchemy as sa
from sqlalchemy import orm

from . import object_handler as oh
from ._db_types import ID, Database, Table, TableName
from ._useful_types import PathType


def _map_type(t: type) -> sa.sql.type_api.TypeEngine:
    if t == int:
        return sa.Integer
    elif t == str:
        return sa.String
    elif t == float:
        return sa.NUMERIC
    elif t == datetime.datetime:
        return sa.DateTime
    elif t == datetime.date:
        return sa.Date
    elif t == pathlib.Path:
        return sa.String
    else:
        type_container = typing.get_origin(t)
        argtypes = [
            argtype for argtype in typing.get_args(t) if argtype is not type(None)
        ]
        if type_container == typing.Union:
            if len(argtypes) != 1:
                raise ValueError(
                    f"Unions other than (type | None) not supported, got: {t}"
                )
            return _map_type(argtypes[0])
        elif type_container in (
            abc.Sequence,
            typing.Sequence,
            abc.Mapping,
            typing.Mapping,
        ):
            return sa.JSON

        raise TypeError(f"Unsupported type: {t}")


def _attr_to_column(a: attrs.Attribute) -> sa.Column:
    name = a.name
    assert a.type is not None
    args: typing.Tuple[typing.Any, ...] = (_map_type(a.type),)
    primary_key = a.metadata.get("primary_key", False)
    nullable = not a.metadata.get("required", False)
    # TODO: Implement foreign key relationships
    # if "foreign_key" in a.metadata:
    #     args += (sa.ForeignKey(a.metadata["foreign_key"]),)
    comment = a.metadata.get("comment", None)

    return sa.Column(
        name, *args, primary_key=primary_key, nullable=nullable, comment=comment
    )


@functools.lru_cache(None)
def _metadata_object() -> sa.MetaData:
    return sa.MetaData()


@functools.lru_cache(None)
def _mapper_registry() -> orm.registry:
    return orm.registry()


@functools.lru_cache(None)
def _map_tables() -> typing.Mapping[TableName, sa.Table]:
    metadata_object = _metadata_object()
    mapper_registry = _mapper_registry()
    table_mapping: typing.Dict[TableName, sa.Table] = {}

    for table_name, base_type in oh.TYPE_MAPPING.items():
        columns = [_attr_to_column(attr) for attr in attrs.fields(base_type)]

        table = sa.Table(table_name, metadata_object, *columns)

        table_mapping[TableName(table_name)] = table

        mapper_registry.map_imperatively(
            base_type,
            table,
        )

    return table_mapping


class SqlDatabaseHandler:
    def __init__(self, db_loc: PathType):
        self._db = db_loc
        self._table_mapping = _map_tables()

    @functools.cached_property
    def engine(self) -> sa.engine.Engine:
        return sa.create_engine(f"sqlite:///{os.fspath(self._db)}", future=True)

    def session(self) -> orm.Session:
        return orm.Session(self.engine)

    def _load_table(self, session: orm.Session, table_type: oh.BaseObject) -> Table:
        query = session.query(table_type)
        return {ID(result.id): result for result in query.all()}

    def load_table(self, table_name: TableName) -> Table:
        with self.session() as session:
            return self._load_table(session, oh.TYPE_MAPPING[table_name])

    def _save_table(
        self, session: orm.Session, table_name: TableName, table_contents: Table
    ) -> None:
        session.add_all(list(table_contents.values()))

    def save_table(self, table_name: TableName, table_contents: Table) -> None:
        _metadata_object().create_all(self.engine)
        with self.session() as session:
            self._save_table(session, table_name, table_contents)
            session.commit()

    def save_database(self, database: Database) -> None:
        _metadata_object().create_all(self.engine)
        with self.session() as session:
            for table_name, contents in database.items():
                self._save_table(session, table_name, contents)

            session.commit()

    def load_database(self) -> Database:
        out: typing.Dict[TableName, Table] = {}
        with self.session() as session:
            for table_name, table_type in oh.TYPE_MAPPING.items():
                out[TableName(table_name)] = self._load_table(session, table_type)
        return out