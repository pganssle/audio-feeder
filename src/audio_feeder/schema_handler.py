"""
Schema handler
"""
import datetime
import functools
import os
import pathlib
import re
import typing

import attr
import attrs
import yaml

from ._useful_types import PathType
from .config import get_configuration

_CONTAINER_MATCH = re.compile("^([a-zA-Z][a-zA-Z0-9]*)\[(.+)\]$")


def _split_type_arguments(arguments: str) -> typing.Sequence[str]:
    bracket_level = 0
    split_point = -1
    for i, c in enumerate(arguments):
        if c == "[":
            bracket_level += 1
        elif c == "]":
            bracket_level -= 1

        if c == "," and bracket_level == 0:
            yield arguments[split_point + 1 : i].strip()
            split_point = i

    yield arguments[split_point + 1 :].strip()


def parse_type(type_str: str) -> type:
    if type_str == "int":
        return int
    elif type_str == "float":
        return float
    elif type_str == "str":
        return str
    elif type_str == "Path":
        return pathlib.Path
    elif type_str == "datetime":
        return datetime.datetime
    elif type_str == "date":
        return datetime.date
    elif (m := _CONTAINER_MATCH.match(type_str)) is not None:
        container, contents = m.groups()
        if container == "Sequence":
            return typing.Sequence[parse_type(contents)]
        elif container == "Mapping":
            key_type, value_type = map(parse_type, _split_type_arguments(contents))
            return typing.Mapping[key_type, value_type]
        elif container == "Union":
            unioned_types = map(parse_type, _split_type_arguments(contents))
            return functools.reduce(lambda a, b: typing.Union[a, b], unioned_types)

    raise ValueError(f"Unknown type: {type_str}")


class TypeEntry(typing.TypedDict, total=False):
    docstring: str
    fields: typing.Sequence[typing.Union[str, attrs.Attribute]]


class SchemaDict(typing.TypedDict):
    tables: typing.Mapping[str, str]
    types: typing.Mapping[str, TypeEntry]


@functools.lru_cache(None)
def _load_schema(schema_file: pathlib.Path) -> SchemaDict:
    with open(schema_file, "r") as sf:
        schema = yaml.safe_load(sf)

    if "tables" not in schema:
        raise ValueError("Tables list missing from schema.")

    if "types" not in schema:
        raise ValueError("Types missing from schema.")

    no_default_sentinel = object()
    schema_out: SchemaDict = {"tables": schema["tables"], "types": {}}
    for type_name, type_entry in schema["types"].items():
        new_type: TypeEntry = {"fields": {}}
        schema_out["types"][type_name] = new_type

        if "docstring" in type_entry:
            new_type["docstring"] = type_entry["docstring"]

        primary_key = type_entry.get("primary_key", "id")
        fields_dict = new_type["fields"]
        for field in type_entry["fields"]:
            if isinstance(field, str):
                field_name = field
                kwargs = {}
            else:
                metadata = {}
                # Field is either a string, a dictionary mapping name to type,
                # or a dictionary mapping name to a dictionary
                if len(field) != 1:
                    raise ValueError(f"Error parsing {field}")
                field_name, value = next(iter(field.items()))
                if isinstance(value, str):
                    field_type = parse_type(value)
                elif isinstance(value, dict):
                    field_type = parse_type(value["type"])

                    for metadata_key in ("comment", "foreign_key", "required"):
                        if metadata_key in value:
                            metadata[metadata_key] = value[metadata_key]
                else:
                    raise ValueError(f"Unknown field format: {field}")

                if not metadata.get("required", False):
                    field_type = typing.Optional[field_type]
                    default = None
                else:
                    default = no_default_sentinel

                kwargs = {"type": field_type, "metadata": metadata}

            if field_name == primary_key:
                if "type" not in kwargs:
                    kwargs["type"] = int
                kwargs.setdefault("metadata", {})["primary_key"] = True

            if default is not no_default_sentinel:
                kwargs["default"] = default

            fields_dict[field_name] = attr.ib(**kwargs)

def load_schema(schema_file: typing.Optional[PathType] = None) -> SchemaDict:
    schema_file = schema_file or get_configuration().schema_loc
    schema_file = pathlib.Path(os.path.abspath(schema_file))

    return _load_schema(pathlib.Path(schema_file))
