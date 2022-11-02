"""
Book handlers
"""

import functools
import typing

import attrs

from ._compat import Self
from ._db_types import TableName
from ._object_types import SchemaObject, SchemaType, TypeName
from .schema_handler import load_schema


def _filter_sparse(_: attrs.Attribute, value: typing.Any) -> bool:
    return value is not None


class BaseObject:
    id: int

    def to_dict(self) -> typing.Mapping[str, typing.Any]:
        return attrs.asdict(self)

    def to_dict_sparse(
        self, *, _filter=_filter_sparse
    ) -> typing.Mapping[str, typing.Any]:
        return attrs.asdict(self, filter=_filter)

    def copy(self: Self) -> Self:
        """Make a new copy of this object."""
        return attrs.evolve(self)


def object_factory(
    name: str,
    properties: typing.Union[
        typing.Sequence[str], typing.Mapping[str, attrs.Attribute]
    ],
    docstring: typing.Optional[str] = None,
) -> SchemaType:
    """
    A function for generating classes from the schema-specified types.
    """
    object_class = attrs.make_class(
        name=name,
        attrs=properties,
        bases=(BaseObject,),
        frozen=False,
        slots=False,  # SqlAlchemy has problems with slots ☹
        repr=True,
    )

    if docstring is not None:
        object_class.__doc__ = docstring

    return object_class


@functools.lru_cache(None)
def load_classes() -> None:
    schema = load_schema()

    type_dict: typing.Dict[TypeName, SchemaType] = {}

    for ctype_name, ctype_def in schema["types"].items():
        # The properties are defined in 'fields'
        if "docstring" in ctype_def:
            docstring: typing.Optional[str] = ctype_def["docstring"]
        else:
            docstring = None

        ctype_props = ctype_def["fields"]

        ctype = object_factory(ctype_name, ctype_props, docstring=docstring)

        type_dict[ctype_name] = ctype

    globals().update(typing.cast(typing.Dict[str, SchemaType], type_dict))

    global TYPE_MAPPING
    TYPE_MAPPING = {}
    TYPE_MAPPING.update(type_dict)


#: The Type Mapping maps the type strings in the schema to the types as loaded.
TYPE_MAPPING: typing.Mapping[TypeName, SchemaType]


# Use the base schema to generate the classes.
def __getattr__(name):
    load_classes()
    global TYPE_MAPPING
    return TYPE_MAPPING

    if name == "TYPE_MAPPING":
        return TYPE_MAPPING
    elif name in TYPE_MAPPING:
        return TYPE_MAPPING[name]

    raise AttributeError(f"module {__name__} has no attribute {name}")
