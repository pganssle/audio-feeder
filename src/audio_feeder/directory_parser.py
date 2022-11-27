import itertools
import os
import pathlib
import re
import typing

from ._useful_types import PathType


class _SupportsSorting(typing.Protocol):
    def __lt__(self, other: typing.Any) -> bool:  # pragma: nocover
        ...


class BaseAudioLoader:
    """
    A base class that defines the interface for all audio loader classes.
    """

    @classmethod
    def is_audio(cls, dirloc: PathType) -> bool:  # pragma: nocover
        raise NotImplementedError("Function must be defined in child classes")

    @classmethod
    def audio_files(
        cls, dir_loc: PathType
    ) -> typing.Sequence[pathlib.Path]:  # pragma: nocover
        raise NotImplementedError("Function must be defined in child classes.")

    @classmethod
    def audio_cover(
        cls, dir_loc: PathType
    ) -> typing.Optional[pathlib.Path]:  # pragma: nocover
        raise NotImplementedError("Function must be defined in child classes.")

    @classmethod
    def parse_creator_names(
        cls, creators: str
    ) -> typing.Sequence[str]:  # pragma: nocover
        raise NotImplementedError("Function must be defined in child classes")

    @classmethod
    def parse_audio_info(
        cls, dir_path: PathType
    ) -> typing.Mapping[str, typing.Any]:  # pragma: nocover
        raise NotImplementedError("Function must be implemented in child classes")

    @classmethod
    def natural_sort_key(cls, value: str) -> _SupportsSorting:
        """
        This is a sort key to do a "natural" lexographic sort, the string is
        broken up into segments of strings and numbers, so that, e.g. `'Str 2'`
        will be sorted before `'Str 15'`.

        :param value:
            The book name as it will be sorted.

        :return:
            Returns a book name tokenized such that it can be sorted.
        """

        # We prepend each string with \0 to ensure that the parity is always
        # the same. The final return value has type (str, int, str, int...),
        # so comparing them always compares strings to strings and ints to
        # ints, so long as we always start with a string. By prepending \0,
        # it makes it so that any strings with integers at the beginning sort
        # before strings with non-integers at the beginning.
        value = "\0" + value

        # First we break the string up into groups by number and string, so:
        # "ab12q" ⇒ ((True, ("a", "b")), (False, ("1", "2")), (True, ("q",)))
        o: typing.Iterable = itertools.groupby(value, key=str.isdecimal)

        # Next we re-stringify the iterables in each group, so:
        # ((True, "ab"), (False, "12"), (True, "q"))
        o = ((k, "".join(g)) for k, g in o)

        # Finally, we turn all the integer strings into actual integers, so that
        # the integers will compare by their number, not by the string.
        o = ((int(v) if k else v) for k, v in o)

        return tuple(o)


class AudiobookLoader(BaseAudioLoader):
    """
    This is a more or less static class that can be used to load audiobooks.
    """

    AUDIO_EXTENSIONS: typing.Final[typing.Sequence[str]] = (
        ".mp3",
        ".mp4",
        ".ogg",
        ".ac3",
        ".aac",
        ".m4b",
        ".m4a",
    )

    COVER_EXTENSIONS: typing.Final[typing.Sequence[str]] = (
        ".png",
        ".jpg",
        ".svg",
        ".gif",
        ".tif",
        ".bmp",
    )

    COVER_PATTERNS: typing.Final[typing.Sequence[re.Pattern]] = [
        re.compile("$.*\-Cover^", re.IGNORECASE),
        re.compile("cover", re.IGNORECASE),
    ]

    DIR_NAME_RE = re.compile(
        "(?P<authors>.+?)(?= \- )"
        + "(?: \- \[(?P<series_name>.*?) (?P<series_number>\d+)\])? \- "
        + "(?P<title>.*$)"
    )

    @classmethod
    def is_audio(cls, dirloc: PathType) -> bool:
        """
        Function to determine if a directory contains an audiobook. The
        assumption is that in this context, any directory containing at least
        one file with the AUDIO_EXTENSIONS is, itself, an audiobook.

        :param dirloc:
            The directory to test.

        :return:
            Returns boolean value whether or not it's an audiobook.
        """
        if not isinstance(dirloc, pathlib.Path):
            dirloc = pathlib.Path(dirloc)

        if dirloc.is_dir():
            return any(
                fpath.suffix.lower() in cls.AUDIO_EXTENSIONS
                for fpath in dirloc.iterdir()
            )

        return False

    @classmethod
    def audio_files(cls, dir_loc: PathType) -> typing.Sequence[pathlib.Path]:
        """
        Load all audiobook files and sort them appropriately.

        :param dir_loc:
            A resolvable path to the directory containing the audiobooks.

        :return:
            Returns a list of audiobook files, sorted appropriately.
        """
        o = []
        for fname in os.listdir(dir_loc):
            _, fname_ext = os.path.splitext(fname)

            if fname_ext in cls.AUDIO_EXTENSIONS:
                o.append(os.path.join(dir_loc, fname))

        return list(map(pathlib.Path, sorted(o, key=cls.natural_sort_key)))

    @classmethod
    def audio_cover(cls, dir_loc: PathType) -> typing.Optional[pathlib.Path]:
        """
        Retrieve the best candidate for an audiobook cover.

        :param dir_loc:
            A resolvable directory containing an audiobook.
        """
        candidates = []
        for fname in os.listdir(dir_loc):
            fname_base, fname_ext = os.path.splitext(fname)
            fname_ext = fname_ext.lower()

            if fname_ext not in cls.COVER_EXTENSIONS:
                continue

            # First sort index is whether it matches one of the cover patterns,
            # and which one.
            match_num = len(cls.COVER_PATTERNS)
            for ii, c_re in enumerate(cls.COVER_PATTERNS):
                if c_re.match(fname_base):
                    match_num = ii
                    break

            # Second sort index is its position in the cover extension index.
            ext_loc = cls.COVER_EXTENSIONS.index(fname_ext)

            candidates.append((match_num, ext_loc, os.path.join(dir_loc, fname)))

        if not len(candidates):
            return None

        _, _, cover_loc = min(candidates)

        return pathlib.Path(cover_loc)

    @classmethod
    def parse_creator_names(cls, creators: str) -> typing.Sequence[str]:
        """
        Splits author names by ',', '&' and 'and'

        :param authors:
            A string containing possibly multiple author names.

        :return:
            Returns a :py:object:`list` of authors.
        """
        o: typing.Iterable[str] = creators.split(" & ")
        o = itertools.chain.from_iterable(x.split(" and ") for x in o)
        o = itertools.chain.from_iterable(x.split(", ") for x in o)

        return list(o)

    @classmethod
    def parse_audio_info(cls, dir_path: PathType) -> typing.Mapping[str, typing.Any]:
        """
        Try to parse audiobook information the directory name.
        """
        dir_name = os.path.basename(dir_path)

        m = cls.DIR_NAME_RE.match(dir_name)
        if m is None:
            msg = f"Directory name does not match the format: {dir_name}"

            raise NoAudiobookInformation(msg)

        authors = cls.parse_creator_names(m.group("authors"))
        series = m.group("series_name")
        series_number = m.group("series_number")
        if series_number is not None:
            series_number = int(series_number)

        title = m.group("title")

        audiobook_data = dict(
            authors=authors, series=(series, series_number), title=title
        )

        return audiobook_data


def load_all_audio(
    base_dir: PathType,
    *,
    visited_dirs: typing.Optional[typing.Set[pathlib.Path]] = None,
    audio_loader_class: typing.Type[BaseAudioLoader] = AudiobookLoader,
) -> typing.Sequence[pathlib.Path]:
    """
    Traverse a directory and find all the directories that contain an
    audiobook (as returned by is_audiobook)

    :param base_dir:
        The base directory in which to search for audiobooks (recursively)

    :param visited_dirs:
        This is an exclusion list of directories not to parse. This function
        is called recursively and ``visited_dirs`` is passed along the call
        stack to prevent infinite recursion.

    :return:
        Returns a :py:object:`list` of directories containing audiobooks.
    """
    # We're not going to use os.walk here because we want to stop drilling
    # down once we've found an audiobook
    base_dir = pathlib.Path(base_dir)
    audiobook_paths = []
    visited_dirs = visited_dirs or set()
    visited_dirs.add(pathlib.Path(os.path.abspath(base_dir)))

    for subdir in base_dir.iterdir():
        dirpath = (base_dir / subdir).absolute()
        if dirpath in visited_dirs or not dirpath.is_dir():
            continue  # Avoid infinite recursion

        if audio_loader_class.is_audio(dirpath):
            audiobook_paths.append(dirpath)
        else:
            audiobook_paths += load_all_audio(
                dirpath,
                visited_dirs=visited_dirs,
                audio_loader_class=audio_loader_class,
            )

    return audiobook_paths


class NoAudiobookInformation(ValueError):
    """Used when a book's directory name does not match the format used."""

    pass
