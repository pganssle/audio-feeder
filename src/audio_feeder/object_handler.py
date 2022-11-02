"""
Book handlers
"""

import typing

import attrs

from .schema_handler import load_schema


def _filter_sparse(_: attrs.Attribute, value: typing.Any) -> bool:
    return value is not None


_Self = typing.TypeVar("_Self", bound="BaseObject")

class BaseObject:
    id: int

    def to_dict(self) -> typing.Mapping[str, typing.Any]:
        return attrs.asdict(self)

    def to_dict_sparse(
        self, *, _filter=_filter_sparse
    ) -> typing.Mapping[str, typing.Any]:
        return attrs.asdict(self, filter=_filter)

    def copy(self: _Self) -> _Self:
        """Make a new copy of this object."""
        return attrs.evolve(self)


def object_factory(
    name: str,
    properties: typing.Union[
        typing.Sequence[str], typing.Mapping[str, attrs.Attribute]
    ],
    docstring: typing.Optional[str] = None,
) -> typing.Type[BaseObject]:
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


def load_classes() -> None:
    schema = load_schema()

    type_dict = {}

    for ctype_name, ctype_def in schema["types"].items():
        # The properties are defined in 'fields'
        if "docstring" in ctype_def:
            docstring: typing.Optional[str] = ctype_def["docstring"]
        else:
            docstring = None

        ctype_props = ctype_def["fields"]

        ctype = object_factory(ctype_name, ctype_props, docstring=docstring)

        type_dict[ctype_name] = ctype

    globals().update(type_dict)

    global TYPE_MAPPING
    TYPE_MAPPING = {}
    TYPE_MAPPING.update(type_dict)


#: The Type Mapping maps the type strings in the schema to the types as loaded.
TYPE_MAPPING: typing.Mapping[str, typing.Type[BaseObject]]


# Use the base schema to generate the classes.
def __getattr__(name):
    if name != "TYPE_MAPPING":
        raise AttributeError(f"module {__name__} has no attribute {name}")

    load_classes()
    global TYPE_MAPPING
    return TYPE_MAPPING
