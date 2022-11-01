import os
import pathlib
import re
import typing
import urllib.parse

from ._useful_types import PathType


class FileLocation:
    """
    This represents a file's location both on disk and as a url. This should be
    considered an immutable object.
    """

    #: This is a regular expression used to split the URL base into <protocol://><url>
    PROTOCOL_SPLIT_RE = re.compile("^(?P<protocol>[^:/]+://)(?P<url>.+)$")

    def __init__(self, rel_path: PathType, url_base: str, path_base: PathType = None):
        """
        :param rel_path:
            The path of the file, relative to both the url_base and the
            path_base.

        :param url_base:
            The base url from which ``rel_path`` is relative as a URL,
            including the protocol.

        :param path_base:
            The base path from which ``rel_path`` is relative as a path on the
            file system.
        """
        if os.path.isabs(rel_path):
            raise InvalidRelativePathError("Path must be relative: {}".format(rel_path))

        protocol_match = self.PROTOCOL_SPLIT_RE.match(url_base)
        if protocol_match is None:
            raise InvalidURLError(
                "URL must be of the form protocol://<url>"
                + ", got: {}".format(url_base)
            )

        self._rel_path = pathlib.Path(rel_path)

        self._url_protocol = protocol_match.group("protocol")
        url_base_bare = protocol_match.group("url")
        if not url_base_bare.endswith("/"):
            url_base_bare += "/"

        # This is a patch until we can do the URL encoding properly later.
        rel_path_url = urllib.parse.quote(os.fspath(rel_path))
        self._url_bare = urllib.parse.urljoin("//" + url_base_bare, rel_path_url)[2:]

        self._url = self._url_protocol + self._url_bare

        if path_base is not None:
            _path_str = os.path.join(path_base, rel_path)
            self._path: typing.Optional[pathlib.Path] = pathlib.Path(
                os.path.normpath(_path_str)
            )
        else:
            self._path = None

    @property
    def url(self) -> str:
        """
        The file location as a url, with the default protocol.
        """
        return self._url

    @property
    def path(self) -> typing.Optional[pathlib.Path]:
        """
        The file location as a path on the file system.
        """
        return self._path

    def url_as_protocol(self, protocol: str) -> str:
        """
        Returns the file's location as a URL using an alternate protocol.

        :param protocol:
            The protocol string to use. If it does not end in ://, :// will be
            appended.
        """
        if not protocol.endswith("://"):
            protocol = protocol + "://"

        return protocol + self._url_bare

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}('{self._rel_path}')>"


class InvalidURLError(ValueError):
    pass


class InvalidRelativePathError(ValueError):
    pass
