import pathlib
import typing

from tests.utils import copy_with_unzip, make_file

TESTS_LOC: typing.Final[pathlib.Path] = pathlib.Path(__file__).parent / "../tests"
TEST_DATA_LOC: typing.Final[pathlib.Path] = TESTS_LOC / "data"

__all__ = ("copy_with_unzip", "make_file")
