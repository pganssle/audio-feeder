"""Database handler using a SQL database"""

import datetime
import functools
import json
import logging
import os
import pathlib
import typing
from collections import abc

import attrs
import sqlalchemy as sa
from sqlalchemy import orm

from . import _object_types as ot
from . import file_probe as fp
from . import object_handler as oh
from ._db_types import ID, Database, Table, TableName
from ._useful_types import PathType

DB_VERSION: typing.Final[int] = 2


class AbsoluteDateTime(sa.types.TypeDecorator):
    impl = sa.types.DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value.tzinfo is None:
            raise TypeError("Cannot bind naïve datetime to AbsoluteDateTime")
        return value.astimezone(datetime.timezone.utc)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=datetime.timezone.utc)


class SQLPath(sa.types.TypeDecorator):
    impl = sa.types.String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return os.fspath(value)

    def process_result_value(self, value, dialect):
        return pathlib.Path(value)


class _CustomEncoder(json.JSONEncoder):
    def _is_custom_type(self, obj: typing.Any) -> bool:
        return isinstance(obj, (os.PathLike, fp.FileInfo))

    def default(self, obj: typing.Any) -> typing.Any:
        if isinstance(obj, os.PathLike):
            return os.fspath(obj)
        if isinstance(obj, fp.FileInfo):
            return obj.to_json()
        return super().default(obj)

    def encode(self, obj: typing.Any) -> str:
        if isinstance(obj, abc.Mapping):
            # Apparently implementing `default()` doesn't work when the object
            # is a dictionary key, but calling `default()` on an already-supported
            # type *also* doesn't work, so we need to check if it's one of the
            # types we've added support for and if so get the serializable
            # version of it.
            return super().encode(
                {
                    self.default(key) if self._is_custom_type(key) else key: value
                    for key, value in obj.items()
                }
            )
        return super().encode(obj)


class _CustomJsonType(sa.types.TypeDecorator):
    impl = sa.types.String
    cache_ok = True

    def _load_json(self, value: str) -> typing.Any:
        if value is None:
            return None

        return json.loads(value)

    # Typing bug in sqlalchemy-stubs
    def process_bind_param(self, value, dialect) -> str:  # type: ignore[override]
        return json.dumps(value, cls=_CustomEncoder)


class _PathCollection(_CustomJsonType):
    def process_result_value(self, value: str, dialect):
        json_obj = self._load_json(value)
        if json_obj is None:
            return None

        if isinstance(json_obj, typing.Sequence):
            return list(map(pathlib.Path, json_obj))
        elif isinstance(json_obj, typing.Mapping):
            return {pathlib.Path(key): value for key, value in json_obj.items()}
        else:
            return json_obj


class _CoverImages(_CustomJsonType):
    def process_result_value(self, value: str, dialect):

        json_obj = self._load_json(value)

        if json_obj is None:
            return None

        # This is Mapping[str, Union[pathlib.Path, Mapping[str, str]]], so each
        # sub-directory is either a dict or a path
        out: typing.Dict[typing.Any, typing.Any] = {}
        for key, value in json_obj.items():
            if isinstance(value, typing.Mapping):
                out[key] = value
            else:
                out[key] = pathlib.Path(value)
        return out


class _FileMetadata(_CustomJsonType):
    def process_result_value(self, value: str, dialect):

        json_obj = self._load_json(value)
        if json_obj is None:
            return None

        return {
            pathlib.Path(key): fp.FileInfo.from_json(value)
            for key, value in json_obj.items()
        }


_NestedType = typing.Union[type, typing.Tuple["_NestedType", ...]]


def _parse_nested_type(t: type) -> _NestedType:
    container_type: typing.Optional[type] = typing.get_origin(t)
    if container_type is None:
        return t

    return (container_type, tuple(map(_parse_nested_type, typing.get_args(t))))


_CanonicalMapType = typing.get_origin(typing.Mapping[None, None])
_CanonicalSequenceType = typing.get_origin(typing.Sequence[None])


def _map_type(t: type) -> typing.Type[sa.sql.type_api.TypeEngine]:
    if t == int or t == ID:
        return sa.Integer
    elif t == str:
        return sa.String
    elif t == float:
        return sa.NUMERIC
    elif t == datetime.datetime:
        return AbsoluteDateTime
    elif t == datetime.date:
        return sa.Date
    elif t == pathlib.Path:
        return SQLPath
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
        elif type_container in (_CanonicalMapType, _CanonicalSequenceType):
            if type_container == _CanonicalSequenceType and argtypes[0] == pathlib.Path:
                return _PathCollection
            if type_container == _CanonicalMapType:
                if argtypes[1] == fp.FileInfo:
                    return _FileMetadata
                if argtypes[0] == pathlib.Path:
                    return _PathCollection
                if argtypes[0] == str:
                    # This may be the problematic "cover images" type
                    nested_type_def = _parse_nested_type(argtypes[1])
                    if nested_type_def == (
                        typing.Union,
                        (pathlib.Path, (_CanonicalMapType, (str, str))),
                    ):
                        return _CoverImages
            return sa.JSON

        raise TypeError(f"Unsupported type: {t}")  # pragma: nocover


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

    for table_name, type_name in oh.TABLE_MAPPING.items():
        base_type = oh.TYPE_MAPPING[type_name]
        # Drop type ignore when attrs >= 22.1 is released
        columns = [_attr_to_column(attr) for attr in attrs.fields(base_type)]  # type: ignore[arg-type]

        table = sa.Table(table_name, metadata_object, *columns)

        table_mapping[TableName(table_name)] = table

        mapper_registry.map_imperatively(
            base_type,
            table,
        )

    return table_mapping


class SqlDatabaseHandler:
    def __init__(self, db_loc: PathType):
        self._db = pathlib.Path(db_loc)
        self._table_mapping = _map_tables()

    @functools.cached_property
    def engine(self) -> sa.engine.Engine:
        return sa.create_engine(f"sqlite:///{os.fspath(self._db)}", future=True)

    def session(self) -> orm.Session:
        return orm.Session(self.engine, expire_on_commit=False)

    def _load_table(self, session: orm.Session, table_type: ot.SchemaType) -> Table:
        query = session.query(table_type)
        return {ID(result.id): result for result in query.all()}

    def _upgrade_version(self, session: orm.Session, old: int) -> None:
        if old < 2:
            logging.info(
                "Database version < 2, adding the files, file_metadata "
                "and file_hashes columns to the entries table."
            )
            session.execute("ALTER TABLE entries ADD COLUMN files JSON")
            session.execute("ALTER TABLE entries ADD COLUMN file_metadata JSON")
            session.execute("ALTER TABLE entries ADD COLUMN file_hashes JSON")

        session.execute(f"PRAGMA user_version={DB_VERSION}")

    def _initialize_db(self) -> None:
        if not self._db.exists():
            _metadata_object().create_all(self.engine)
            with self.session() as session:
                session.execute(f"PRAGMA user_version={DB_VERSION}")
        else:
            with self.session() as session:
                db_version: int = session.execute("PRAGMA user_version").first()[0]  # type: ignore[index]
                if db_version < DB_VERSION:
                    logging.info(
                        "Upgrading database from %s to %s", db_version, DB_VERSION
                    )
                    self._upgrade_version(session, db_version)
                elif db_version > DB_VERSION:
                    raise ValueError(
                        f"Database version {db_version} is greater than the "
                        + f"highest version supported by this application ({DB_VERSION})"
                    )

    def load_table(self, table_name: TableName) -> Table:
        with self.session() as session:
            type_name = oh.TABLE_MAPPING[table_name]
            return self._load_table(session, oh.TYPE_MAPPING[type_name])

    def _save_table(
        self, session: orm.Session, table_name: TableName, table_contents: Table
    ) -> None:
        table_type = oh.TYPE_MAPPING[oh.TABLE_MAPPING[table_name]]

        stmt = sa.delete(table_type).where(
            sa.column("id").not_in(table_contents.keys())
        )
        session.execute(stmt)

        try:
            session.add_all(list(table_contents.values()))
        except orm.exc.UnmappedInstanceError:
            # If the instances were created before the ORM mapping was set up,
            # instrumentation won't be set up on the instances, so we need to
            # create new copies of the instances (at least until we find a
            # better way to do this.
            session.add_all(
                [table_entry.copy() for table_entry in table_contents.values()]
            )

    def save_table(self, table_name: TableName, table_contents: Table) -> None:
        with self.session() as session:
            self._save_table(session, table_name, table_contents)
            session.commit()

    def save_database(self, database: Database) -> None:
        self._initialize_db()
        with self.session() as session:
            for table_name, contents in database.items():
                self._save_table(session, table_name, contents)

            session.commit()

    def load_database(self) -> Database:
        self._initialize_db()
        out: typing.Dict[TableName, Table] = {}
        with self.session() as session:
            for table_name, type_name in oh.TABLE_MAPPING.items():
                table_type = oh.TYPE_MAPPING[type_name]
                out[TableName(table_name)] = self._load_table(session, table_type)
        return out
