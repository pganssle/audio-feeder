"""
Configuration manager - handles the application's global configuration.
"""
import base64
import hashlib
import logging
import os
import pathlib
import typing
import warnings
from collections import OrderedDict
from itertools import product

import yaml

from ._useful_types import PathType
from .file_location import FileLocation

CONFIG_DIRS = [pathlib.Path.cwd()] + [
    pathlib.Path(os.path.expanduser(x))
    for x in (
        "/etc/audio_feeder/",
        "~/.config/audio_feeder/",
    )
]

CONFIG_NAMES = ["config.yml"]
CONFIG_LOCATIONS = list(
    (bdir / cfile) for bdir, cfile in product(CONFIG_DIRS, CONFIG_NAMES)
)


class _ConfigProperty:
    def __init__(self, prop_name):
        self.prop_name = prop_name

    def __repr__(self):
        return self.__class__.__name__ + "({})".format(self.prop_name)


class Configuration:
    PROPERTIES = OrderedDict(
        (
            ("base_truncation_point", 500),
            ("templates_base_loc", "{{CONFIG}}/templates"),
            ("entry_templates_loc", "{{TEMPLATES}}/entry_types"),
            ("pages_templates_loc", "{{TEMPLATES}}/pages"),
            ("rss_templates_loc", "{{TEMPLATES}}/rss"),
            ("rss_entry_templates_loc", "{{TEMPLATES}}/rss/entry_types"),
            # Deprecated — No longer has any effect
            ("schema_loc", "{{CONFIG}}/database/schema.yml"),
            ("database_loc", "{{CONFIG}}/database/db"),
            ("static_media_path", "{{CONFIG}}/static"),
            ("static_media_url", "{{URL}}/static"),
            # Relative to static
            ("media_path", "media"),
            ("site_images_loc", "images/site-images"),
            ("qr_cache_path", "images/qr_cache"),
            ("cover_cache_path", "images/entry_cover_cache"),
            ("css_loc", "css"),
            # Relative to base
            ("rss_feed_urls", "rss/{id}.xml"),
            # Relative to others
            ("main_css_files", ["main.css", "fontawesome-subset.css"]),  # CSS
            ("thumb_max", [200, 400]),  # width, height
            ("base_protocol", "http"),
            ("base_host", "localhost"),
            ("base_port", 9090),
            # API Keys
            ("google_api_key", None),
        )
    )

    REPLACEMENTS = {
        "{{CONFIG}}": _ConfigProperty("config_directory"),
        "{{TEMPLATES}}": _ConfigProperty("templates_base_loc"),
        "{{STATIC}}": _ConfigProperty("static_media_path"),
        "{{URL}}": _ConfigProperty("base_url"),
    }

    def __init__(self, config_loc_: typing.Optional[PathType] = None, **kwargs):
        if config_loc_ is None:
            # If configuration location is not specified, we'll use pwd.
            config_loc_ = pathlib.Path.cwd() / "config.yml"

        self.config_location: pathlib.Path = pathlib.Path(config_loc_)
        self.config_directory: pathlib.Path = self.config_location.parent

        base_kwarg = self.PROPERTIES.copy()

        for kwarg in kwargs.keys():
            if kwarg not in self.PROPERTIES:
                raise TypeError("Unexpected keyword argument: {}".format(kwarg))

        base_kwarg.update(kwargs)

        kwargs = base_kwarg

        self._base_dict = {}
        for kwarg in self.PROPERTIES.keys():
            value = kwargs[kwarg]
            setattr(self, kwarg, value)
            self._base_dict[kwarg] = value

        if self.base_port is None:
            self.base_url = self.base_host
        else:
            self.base_url = "{}:{}".format(self.base_host, self.base_port)

        self.base_url = self.base_protocol + "://" + self.base_url
        self.url_id = self.hash_encode(self.base_url)

        for kwarg in self.PROPERTIES.keys():
            setattr(self, kwarg, self.make_replacements(getattr(self, kwarg)))

        self.media_loc = FileLocation(
            self.media_path, self.static_media_url, self.static_media_path
        )

    @classmethod
    def from_file(cls, file_loc, **kwargs):
        if not os.path.exists(file_loc):
            raise IOError("File not found: {}".format(file_loc))

        with open(file_loc, "r") as yf:
            config = yaml.safe_load(yf)

        config.update(kwargs)

        return cls(config_loc_=file_loc, **config)

    def to_file(self, file_loc):
        """
        Dumps the configuration to a YAML file in the specified location.

        This will not reflect any runtime modifications to the configuration
        object.
        """
        with open(file_loc, "w") as yf:
            yaml.dump(self._base_dict, stream=yf, default_flow_style=False)

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, *args):
        return getattr(self, key, *args)

    def keys(self):
        return self.PROPERTIES.keys()

    def values(self):
        return (self.get(k) for k in self.keys())

    def items(self):
        return ((k, self.get(k)) for k in self.keys())

    def hash_encode(self, str_data):
        """
        Encode some string data as a base64-encoded hash.

        This is not intended to be super robust, but it should work for the
        purposes of creating a reproducible number from input parameters.
        """
        h = hashlib.sha256()
        h.update(str_data.encode("utf-8"))

        return base64.b64encode(h.digest())[0:16].decode("utf-8")

    def make_replacements(self, value):
        if not isinstance(value, str):
            return value

        for k, repl in self.REPLACEMENTS.items():
            if k not in value:
                continue

            if isinstance(repl, _ConfigProperty):
                repl = self.get(repl.prop_name)

            if isinstance(repl, os.PathLike):
                repl = os.fspath(repl)

            return value.replace(k, repl)

        return value

    def to_dict(self):
        return dict(*self.items())


def init_config(
    config_loc: typing.Optional[PathType] = None,
    config_loc_must_exist: bool = False,
    **kwargs
):
    """
    Initializes the configuration from config_loc or from the default
    configuration location.
    """

    found_config = False
    if config_loc is not None:
        if not os.path.exists(config_loc):
            if config_loc_must_exist:
                raise MissingConfigError("Configuration location does not exist.")

            # Make sure we can write to this directory
            if not os.access(os.path.split(config_loc)[0], os.W_OK):
                msg = "Cannot write to {}".format(config_loc)
                raise ConfigWritePermissionsError(msg)
        config_location = config_loc
        found_config = True
    else:
        config_location = os.environ.get("AUDIO_FEEDER_CONFIG", None)
        falling_back = False
        found_config = False
        if config_location is not None:
            if not os.path.exists(config_location):
                falling_back = True
            else:
                found_config = True

        if not found_config:
            config_locs = [config_location] if config_location else []
            for config_location in CONFIG_LOCATIONS:
                config_locs.append(config_location)
                if os.path.exists(config_location):
                    found_config = True
                    break

        if falling_back:
            msg = (
                "Could not find config file from environment variable:"
                + " {},".format(os.environ["AUDIO_RSS_CONFIG"])
            )
            if found_config:
                msg += ", using {} instead.".format(config_location)
            else:
                msg += ", using baseline configuration."

            warnings.warn(msg, RuntimeWarning)

    if found_config and os.path.exists(config_location):
        new_conf = Configuration.from_file(config_location, **kwargs)
        get_configuration._configuration = new_conf
    else:
        if not found_config:
            for config_location in config_locs:
                if not os.fspath(config_location).endswith(".yml"):
                    continue

                config_dir = os.path.split(config_location)[0]
                if os.access(config_dir, os.W_OK):
                    break
            else:
                config_location = None

        new_conf = Configuration(config_loc_=config_location, **kwargs)
        get_configuration._configuration = new_conf

        if config_location is not None:
            logging.info("Creating configuration file at {}".format(config_location))

            get_configuration._configuration.to_file(config_location)


def get_configuration() -> Configuration:
    """
    On first call, this loads the configuration object, on subsequent calls,
    this returns the original configuration object.
    """
    config_obj = getattr(get_configuration, "_configuration", None)
    if config_obj is not None:
        return config_obj

    init_config()

    return get_configuration._configuration


def read_from_config(field):
    """
    Convenience method for accessing specific fields from the configuration
    object.
    """
    return get_configuration()[field]


class MissingConfigError(ValueError):
    pass


class ConfigWritePermissionsError(ValueError):
    pass
