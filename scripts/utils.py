import os
import pathlib
import sys
import typing

TESTS_LOC: typing.Final[pathlib.Path] = pathlib.Path(__file__).parent / "../tests"
TEST_DATA_LOC: typing.Final[pathlib.Path] = TESTS_LOC / "data"


sys.path.append(os.fspath(TESTS_LOC))

from utils import copy_with_unzip, make_file  # type: ignore[import]

sys.path.pop(sys.path.index(os.fspath(TESTS_LOC)))

__all__ = ("copy_with_unzip", "make_file")
