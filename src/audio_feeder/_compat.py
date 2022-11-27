try:
    from typing import Self  # type: ignore[attr-defined]
except ImportError:
    from typing_extensions import Self

try:
    from enum import StrEnum  # type: ignore[attr-defined]
except ImportError:
    from backports.strenum import StrEnum  # type: ignore[import]

__all__ = ("Self", "StrEnum")
