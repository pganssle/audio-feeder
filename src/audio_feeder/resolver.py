import functools
import os
import pathlib
import typing

import qrcode
from qrcode.image.svg import SvgPathImage

from . import cache_utils
from ._useful_types import PathType
from .config import Configuration, get_configuration
from .file_location import FileLocation


class Resolver:
    """
    Often it is necessary to interact with files both in the file system and as
    a URL. The Resolver class retrieves the proper URLs from the configuration
    files and resolves them as :class:`Resolved` objects.
    """

    def __init__(
        self,
        config: typing.Optional[Configuration] = None,
        qr_generator: typing.Optional["QRGenerator"] = None,
    ):
        if config is None:
            config = get_configuration()

        self.base_url = config.base_url
        self.static_url = config.static_media_url

        self.base_path = config.config_directory
        self.static_path = config.static_media_path

        self.media_path = config.media_path
        self.media_cache_path = config.media_cache_path

        self._config = config

        if qr_generator is None:
            self.qr_generator = QRGenerator()

    def resolve_rss(self, entry_obj, tail: typing.Optional[str] = None) -> FileLocation:
        kwargs = dict(id=entry_obj.id, table=entry_obj.table, tail=tail or "")

        # In the config, the RSS feeds will be specified relative to
        # the base URL.
        url_tail = self._config.rss_feed_urls.format(**kwargs)

        # Doesn't represent a location on disk, so base_path is None
        return FileLocation(url_tail, self.base_url, None)

    def resolve_qr(
        self, e_id: int, url: str, mode: typing.Optional[str] = None
    ) -> FileLocation:
        # Check the QR cache - for the moment, we're going to assume that once
        # a QR code is generated, it's accurate until it's deleted. Eventually
        # it might be nice to allow multiple caches.

        # There's a unique QR cache location for each base URL.
        qr_cache_loc = self._config.qr_cache_path
        qr_cache_loc = os.path.join(qr_cache_loc, self._config.url_id)

        if mode is None:
            file_name = f"{e_id}"
        else:
            file_name = f"{e_id}-{mode}"
        rel_save_path = self.qr_generator.get_save_path(qr_cache_loc, file_name)

        qr_fl = FileLocation(rel_save_path, self.static_url, self.static_path)

        qr_fl_path = qr_fl.path

        # This should always be true if path_base is specified for FileLocation
        assert qr_fl_path is not None
        if not qr_fl_path.exists():
            qr_cache_loc_full = qr_fl_path.parent
            if not qr_cache_loc_full.exists():
                qr_cache_loc_full.mkdir(parents=True)

            self.qr_generator.generate_qr(url, qr_fl_path)

        return qr_fl

    def resolve_chapter(self, entry_obj, guid: str) -> FileLocation:
        url_tail = f"chapter-data/{entry_obj.id}-{guid}.json"

        # Doesn't represent a location on disk, so base_path is None
        return FileLocation(url_tail, self.base_url, None)

    def resolve_media_cache(self, url_tail: str) -> FileLocation:
        media_rel = os.path.join(self.media_cache_path, url_tail)
        return self.resolve_static(media_rel)

    def resolve_media(self, url_tail: str) -> FileLocation:
        media_rel = os.path.join(self.media_path, url_tail)
        return self.resolve_static(media_rel)

    def resolve_static(self, url_tail: str) -> FileLocation:
        return FileLocation(url_tail, self.static_url, self.static_path)


class QRGenerator:
    """
    Class for generating QR codes on demand
    """

    def __init__(
        self, fmt: str = "png", version: typing.Optional[int] = None, **qr_options
    ):
        if fmt == "svg":
            image_factory = SvgPathImage
            self.extension: str = ".svg"
        elif fmt == "png":
            image_factory = None
            self.extension = ".png"

        qr_options["version"] = version
        qr_options["image_factory"] = image_factory

        qr_options.setdefault("border", 0)
        self.qr_options: typing.Mapping[str, typing.Any] = qr_options

    def generate_qr(self, data: str, save_path: PathType) -> None:
        img = qrcode.make(data, **self.qr_options)
        img.save(save_path)

    def get_save_path(self, save_dir, save_name) -> pathlib.Path:
        save_path = pathlib.Path(save_dir) / (save_name + self.extension)

        return save_path


###
# Functions
@cache_utils.register_function_cache("config")
@functools.lru_cache(None)
def get_resolver() -> Resolver:
    """
    Retrieves a cached singleton Resolver object.
    """
    return Resolver()
