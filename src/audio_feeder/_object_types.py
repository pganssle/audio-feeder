"""Protocols to cover the schema objects.

This is partially to allow typing without circular imports and partially to
allow typing on the generated schema types.
"""
import typing

from ._compat import Self


# TODO: When attrs > 22.1 is released, this should be an AttrsInstance
class SchemaObject(typing.Protocol):
    id: int

    def to_dict(self) -> typing.Mapping[str, typing.Any]:
        ...

    def to_dict_sparse(
        self, *, _filter: typing.Callable = ...
    ) -> typing.Mapping[str, typing.Any]:
        ...

    def copy(self: Self) -> Self:
        """Make a new copy of this object."""
        ...


SchemaType = typing.Type[SchemaObject]
TypeName = typing.NewType("TypeName", str)
