#! /usr/bin/env python3
import os
import re
from urllib.parse import urljoin

import qrcode
from qrcode.image.svg import SvgPathImage


class Resolver:
    """
    Often it is necessary to interact with files both in the file system and as
    a URL. The Resolver class retrieves the proper URLs from the configuration
    files and resolves them as :class:`Resolved` objects.
    """
    def __init__(self, config=None, qr_generator=None):
        if config is None:
            from .config import get_configuration

            config = get_configuration()

        self.base_url = config.base_url
        self.static_url = config.static_media_url

        self.base_path = config.config_directory
        self.static_path = config.static_media_path

        self.media_path = config.media_path

        self._config = config

        if qr_generator is None:
            self.qr_generator = QRGenerator()

    def resolve_rss(self, entry_obj, tail=None):
        kwargs = dict(id=entry_obj.id, table=entry_obj.table, tail=tail or '')

        # In the config, the RSS feeds will be specified relative to
        # the base URL.
        url_tail = self._config.rss_feed_urls.format(**kwargs)

        # Doesn't represent a location on disk, so base_path is None
        return FileLocation(url_tail, self.base_url, None)

    def resolve_qr(self, e_id, url):
        # Check the QR cache - for the moment, we're going to assume that once
        # a QR code is generated, it's accurate until it's deleted. Eventually
        # it might be nice to allow multiple caches.

        qr_cache_loc = self._config.qr_cache_path

        rel_save_path = self.qr_generator.get_save_path(qr_cache_loc,
                                                        '{}'.format(e_id))

        qr_fl = FileLocation(rel_save_path, self.static_url, self.static_path)
        if not os.path.exists(qr_fl.path):
            self.qr_generator.generate_qr(url, qr_fl.path)

        return qr_fl

    def resolve_media(self, url_tail):
        media_rel = os.path.join(self.media_path, url_tail)
        return self.resolve_static(media_rel)

    def resolve_static(self, url_tail):
        return FileLocation(url_tail, self.static_url, self.static_path)


class FileLocation:
    """
    This represents a file's location both on disk and as a url. This should be
    considered an immutable object.
    """
    #: This is a regular expression used to split the URL base into <protocol://><url>
    PROTOCOL_SPLIT_RE = re.compile('^(?P<protocol>[^:/]+://)(?P<url>.+)$')

    def __init__(self, rel_path, url_base, path_base=None):
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
            raise InvalidRelativePathError('Path must be relative: {}'.format(rel_path))

        protocol_match = self.PROTOCOL_SPLIT_RE.match(url_base)
        if protocol_match is None:
            raise InvalidURLError('URL must be of the form protocol://<url>' +
                                  ', got: {}'.format(url_base))

        self._rel_path = rel_path

        self._url_protocol = protocol_match.group('protocol')
        url_base_bare = protocol_match.group('url')
        if not url_base_bare.endswith('/'):
            url_base_bare += '/'

        # This is a patch until we can do the URL encoding properly later.
        rel_path_url = rel_path.replace(' ', "%20")
        self._url_bare = urljoin('//' + url_base_bare, rel_path_url)[2:]

        self._url = self._url_protocol + self._url_bare

        if path_base is not None:
            self._path = os.path.join(path_base, rel_path)
            self._path = os.path.normpath(self._path)
        else:
            self._path = None

    @property
    def url(self):
        """
        The file location as a url, with the default protocol.
        """
        return self._url

    @property
    def path(self):
        """
        The file location as a path on the file system.
        """
        return self._path

    def url_as_protocol(self, protocol):
        """
        Returns the file's location as a URL using an alternate protocol.

        :param protocol:
            The protocol string to use. If it does not end in ://, :// will be
            appended.
        """
        if not protocol.endswith('://'):
            protocol = protocol + '://'

        return protocol + self._url_bare

    def __repr__(self):
        return "<{name}('{rel_path}')>".format(
            name=self.__class__.__name__,
            rel_path=self._rel_path
        )


class QRGenerator:
    """
    Class for generating QR codes on demand
    """
    def __init__(self, fmt='png', version=None, **qr_options):
        if fmt == 'svg':
            image_factory = SvgPathImage
            self.extension = '.svg'
        elif fmt == 'png':
            image_factory = None
            self.extension = '.png'

        qr_options['version'] = version
        qr_options['image_factory'] = image_factory

        qr_options.setdefault('border', 0)
        self.qr_options = qr_options

    def generate_qr(self, data, save_path):
        img = qrcode.make(data, **self.qr_options)
        img.save(save_path)

    def get_save_path(self, save_dir, save_name):
        save_path = os.path.join(save_dir, save_name + self.extension)

        return save_path

###
# Functions
def get_resolver():
    """
    Retrieves a cached singleton Resolver object.
    """
    try:
        resolver = getattr(get_resolver, '_resolver')
    except AttributeError:
        resolver = Resolver()
        get_resolver._resolver = resolver

    return resolver


class InvalidURLError(ValueError):
    pass

class InvalidRelativePathError(ValueError):
    pass
