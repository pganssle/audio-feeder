#! /usr/bin/env python3 -O

# This needs to be run with -O because there's some erroneous assertion in
# the fontTools library.
import functools
import operator
import os
import pathlib
import re
import sys
import tempfile
import typing
import urllib.parse

import click
import fontTools.merge  # type: ignore
import fontTools.subset  # type: ignore

DESIRED_ICONS: typing.Sequence[str] = [
    "angle-double-left",
    "angle-left",
    "angle-double-right",
    "angle-right",
    "bars",
    "gear",
    "user",
    "arrow-down-wide-short",
    "filter",
    "qrcode",
    "square-rss",
]

FONT_FAMILY: typing.Final[str] = "FontAwesomeSubset"

FONT_DEFINITION: typing.Final[
    str
] = f"""@font-face {{{{
  font-family: '{FONT_FAMILY}';
  src:
{{flavors}};
}}}}
"""

CSS_START: typing.Final[
    str
] = """.fa,
.fas,
.far,
.fal,
.fab {
  -moz-osx-font-smoothing: grayscale;
  -webkit-font-smoothing: antialiased;
  display: inline-block;
  font-style: normal;
  font-variant: normal;
  text-rendering: auto;
  line-height: 1;
  font-family: 'FontAwesomeSubset'; }
"""

CSS_BASE: typing.Final[
    str
] = """.fa-{icon}:before {{
    content: "\\{codepoint}"; }}
"""


def extract_font_awesome(icon: str, css: str) -> str:
    name = f".fa-{icon}"

    m = re.search(
        name + r":+before {\s+content: " "['\"]+(?P<codepoint>[^'\"]+)",
        css,
        re.MULTILINE,
    )

    if m is None:
        raise ValueError(f"Unknown icon: {icon}")

    codepoint = m.group("codepoint")
    if codepoint.startswith("\\"):
        codepoint = codepoint[1:]

    return codepoint


def load_codepoints(
    css_file: pathlib.Path, icons: typing.Sequence[str] = DESIRED_ICONS
) -> typing.Mapping[str, str]:
    with open(css_file, "r") as f:
        css = f.read()
        codepoints = {icon: extract_font_awesome(icon, css) for icon in icons}

    if "rss" in codepoints:
        # Apparently uBlock is blocking .fa-rss (at least for me)
        codepoints["rss-mod"] = codepoints["rss"]
        del codepoints["rss"]

    return codepoints


def generate_css(
    codepoints: typing.Mapping[str, str],
    font_flavors: typing.Sequence[tuple[str, str]],
    font_locs: pathlib.Path = pathlib.Path("../fonts/"),
) -> str:
    font_flavors_in = [
        (font_locs / output_name, flavor) for output_name, flavor in font_flavors
    ]

    font_inputs = ",\n".join(
        [
            f"    url('{font_loc}') format('{flavor}')"
            for font_loc, flavor in font_flavors_in
        ]
    )

    css = [FONT_DEFINITION.format(flavors=font_inputs), CSS_START]

    css += [
        CSS_BASE.format(icon=icon, codepoint=codepoint)
        for icon, codepoint in codepoints.items()
    ]

    return "\n".join(css)


def generate_subset_font(
    input_fonts: typing.Sequence[pathlib.Path],
    codepoints: typing.Mapping[str, str],
    output_loc: pathlib.Path,
    flavors: typing.Sequence[str] = ("woff2", "woff"),
) -> typing.Sequence[tuple[str, str]]:
    codepoints_str = ",".join(("U+" + cp) for cp in codepoints.values())

    with tempfile.TemporaryDirectory() as tdir_s:
        tdir = pathlib.Path(tdir_s)
        # Create subsets of all the input fonts
        font_outputs = []
        for font_in in input_fonts:
            font_path = os.fspath(font_in)
            out_name = font_in.stem + ".sub" + font_in.suffix
            font_out = tdir / out_name

            fontTools.subset.main(
                args=(
                    font_path,
                    f"--output-file={font_out}",
                    f"--unicodes={codepoints_str}",
                )
            )

            font_outputs.append(font_out)

        # Merge them into a single font output
        merger = fontTools.merge.Merger()
        font = merger.merge(font_outputs)
        flavors_out = []
        for flavor in flavors:
            font.flavor = flavor
            out_path = output_loc.with_suffix(f".{flavor}")
            flavors_out.append((out_path.name, flavor))
            font.save(out_path)

        return flavors_out


def bad_options(message: str) -> typing.NoReturn:
    print(message)
    sys.exit(1)


ExistingDir = click.Path(
    dir_okay=True, file_okay=False, exists=True, path_type=pathlib.Path
)  # type: ignore
ExistingFileOrDir = click.Path(
    dir_okay=True, file_okay=True, exists=True, path_type=pathlib.Path
)  # type: ignore
FA_VERSION_TEMPLATE: typing.Final[
    str
] = "https://use.fontawesome.com/releases/v{version}/fontawesome-free-{version}-web.zip"
LATEST_FA_VERSION: typing.Final[str] = "6.2.0"


@click.command()
@click.option("--output", type=ExistingDir, default=None)
@click.option("--css-output", type=ExistingDir, default=None)
@click.option("--font-output", type=ExistingDir, default=None)
@click.option("--font-awesome", type=ExistingFileOrDir, default=None)
@click.option("--font-awesome-url", type=str, default=None)
@click.option("--font-awesome-version", type=str, default=None)
def main(
    output: pathlib.Path | None,
    css_output: pathlib.Path | None,
    font_output: pathlib.Path | None,
    font_awesome: pathlib.Path | None,
    font_awesome_url: str | None,
    font_awesome_version: str | None,
) -> None:
    # Handle mutually exclusive options
    if (output is not None) and ((css_output is not None) or (font_output is not None)):
        bad_options(
            "May specify either --output OR --css-output and --font-output, but not both"
        )
    elif (css_output is not None) != (font_output is not None):
        bad_options(
            "Both or neither of -css-output and --font-output must be specified, not just one"
        )

    if (
        num_fa_specified := sum(
            map(
                functools.partial(operator.is_not, None),
                (font_awesome, font_awesome_url, font_awesome_version),
            )
        )
    ) > 1:
        bad_options(
            f"May specify either 0 or 1 of --font-awesome, --font-awesome-url, --font-awesome-version, but specified {num_fa_specified}"
        )
    elif num_fa_specified == 0:
        font_awesome_version = LATEST_FA_VERSION

    if css_output is not None:
        assert font_output is not None
        css_loc: pathlib.Path = css_output
        fonts_loc: pathlib.Path = font_output
    else:
        if output is None:
            output = pathlib.Path(__file__).parent.parent / "src/audio_feeder/data/site"
        css_loc = output / "css"
        fonts_loc = output / "fonts"

    if font_awesome_version is not None:
        font_awesome_url = FA_VERSION_TEMPLATE.format(version=font_awesome_version)

    if font_awesome_url is not None:
        temp_path = pathlib.Path(tempfile.gettempdir())
        filename = pathlib.Path(urllib.parse.urlparse(font_awesome_url).path).name

        font_awesome = temp_path / f"fa_subset_fa/{filename}"
        font_awesome.parent.mkdir(exist_ok=True)

        if not font_awesome.exists():
            import requests

            r = requests.get(font_awesome_url)
            r.raise_for_status()
            font_awesome.write_bytes(r.content)

    assert font_awesome is not None
    if font_awesome.suffix == ".zip":
        import zipfile

        fa_dir: pathlib.Path = font_awesome.with_suffix("")
        if not fa_dir.exists():
            with zipfile.ZipFile(font_awesome, "r") as zf:
                fa_dir.mkdir()
                zf.extractall(fa_dir)
    else:
        fa_dir = font_awesome

    # We assume there's exactly one /css directory in the structure
    (fa_css_dir,) = fa_dir.glob("**/css")
    fa_base_dir = fa_css_dir.parent
    fa_font_dir = fa_base_dir / "webfonts"

    fa_css_file = fa_css_dir / "fontawesome.css"
    input_fonts = [fa_font_dir / font_fname for font_fname in ("fa-solid-900.ttf",)]

    css_out = css_loc / "fontawesome-subset.css"
    font_out = fonts_loc / "fontawesome-subset"

    codepoints = load_codepoints(fa_css_file)
    font_flavors = generate_subset_font(input_fonts, codepoints, font_out)

    css = generate_css(codepoints, font_flavors)

    css_out.write_text(css)


if __name__ == "__main__":
    main()
