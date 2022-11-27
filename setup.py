import itertools
import pathlib
import re
import typing

from setuptools import setup

ROOT: typing.Final[pathlib.Path] = pathlib.Path(__file__).parent


def strip_images(rst_file: pathlib.Path) -> str:
    pattern = re.compile(r"(?P<whitespace>\s*).. image:: (?P<path>.*)$")
    text = rst_file.read_text()
    lines = text.split("\n")
    lines_out = []
    in_block = False
    indent = None
    for line in lines:
        if pattern.match(line):
            in_block = True
            continue
        else:
            if in_block:
                prefix_m = re.match("\s+", line)
                if not prefix_m or (
                    (indent is not None) and indent != line[slice(*prefix_m.span())]
                ):
                    in_block = False
                    indent = None
                else:
                    if indent is None:
                        indent = line[slice(*prefix_m.span())]
                    continue

        lines_out.append(line)

    lines_with_newlines = itertools.groupby(lines_out, key=bool)
    lines_with_collapsed_newlines = (
        grp if has_contents else ("",) for has_contents, grp in lines_with_newlines
    )
    return "\n".join(itertools.chain.from_iterable(lines_with_collapsed_newlines))


setup(
    long_description=strip_images(ROOT / "README.rst"),
    long_description_content_type="text/x-rst",
)
