"""
Book handlers
"""

import typing

import attrs

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
        slots=True,
        eq=True,
        repr=True,
        cmp=False,
        hash=False,
    )

    if docstring is not None:
        object_class.__doc__ = docstring

    return object_class


def load_classes(schema=None) -> None:
    args = (schema,) if schema else tuple()
    schema = load_schema(*args)

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
TYPE_MAPPING: typing.Mapping[str, BaseObject]


# Use the base schema to generate the classes.
def __getattr__(name):
    if name != "TYPE_MAPPING":
        raise AttributeError(f"module {__name__} has no attribute {name}")

    load_classes()
    global TYPE_MAPPING
    return TYPE_MAPPING
