"""Protocols to cover the schema objects.

This is partially to allow typing without circular imports and partially to
allow typing on the generated schema types.
"""

from collections.abc import Callable, Mapping
from typing import Any, NewType, Protocol, Self

ID = NewType("ID", int)


# TODO: When attrs > 22.1 is released, this should be an AttrsInstance
# pragma: nocover
class SchemaObject(Protocol):
    id: ID

    def to_dict(self) -> Mapping[str, Any]: ...

    def to_dict_sparse(self, *, _filter: Callable = ...) -> Mapping[str, Any]: ...

    def copy(self: Self) -> Self:
        """Make a new copy of this object."""
        ...


SchemaType = type[SchemaObject]
TypeName = NewType("TypeName", str)
