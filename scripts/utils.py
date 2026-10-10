import pathlib
from typing import Final

from tests.utils import copy_with_unzip, make_file

TESTS_LOC: Final[pathlib.Path] = pathlib.Path(__file__).parent / "../tests"
TEST_DATA_LOC: Final[pathlib.Path] = TESTS_LOC / "data"

__all__ = ("copy_with_unzip", "make_file")
