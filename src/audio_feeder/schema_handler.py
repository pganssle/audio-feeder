"""
Schema handler
"""
import os
import pathlib
import typing

from ruamel import yaml

from ._useful_types import PathType
from .config import get_configuration


class TypeEntry(typing.TypedDict, total=False):
    docstring: str
    fields: typing.Sequence[str]


class SchemaDict(typing.TypedDict):
    tables: typing.Mapping[str, str]
    types: typing.Mapping[str, TypeEntry]


def load_schema(schema_file: typing.Optional[PathType] = None) -> SchemaDict:
    schema_file = schema_file or get_configuration().schema_loc
    schema_file = pathlib.Path(os.path.abspath(schema_file))

    schema_cache = getattr(load_schema, "_schemas", {})
    if schema_file in schema_cache:
        return schema_cache[schema_file]

    with open(schema_file, "r") as sf:
        schema = yaml.safe_load(sf)

    if "tables" not in schema:
        raise ValueError("Tables list missing from schema.")

    if "types" not in schema:
        raise ValueError("Types missing from schema.")

    schema_cache[schema_file] = schema

    return schema_cache[schema_file]
