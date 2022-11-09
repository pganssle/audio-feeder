"""
Configuration manager - handles the application's global configuration.
"""
import base64
import functools
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

CONFIG_NAMES: typing.Final[typing.Sequence[str]] = ["config.yml"]
DEFAULT_CONFIG_LOCS: typing.Final[typing.Sequence[str]] = [
    "/etc/audio_feeder",
    "~/.config/audio_feeder",
]


def config_dirs(with_pwd=True) -> typing.Sequence[pathlib.Path]:
    if (config_env_var := os.environ.get("AF_CONFIG_DIR", None)) is not None:
        return (pathlib.Path(config_env_var),)

    if with_pwd:
        out = [pathlib.Path.cwd()]
    else:
        out = []

    out.extend(map(pathlib.Path, map(os.path.expanduser, DEFAULT_CONFIG_LOCS)))  # type: ignore[arg-type]
    return out


def config_locations(with_pwd=True) -> typing.Sequence[pathlib.Path]:
    return [
        (bdir / cfile) for bdir, cfile in product(config_dirs(with_pwd), CONFIG_NAMES)
    ]


class _ConfigProperty:
    def __init__(self, prop_name):
        self.prop_name = prop_name

    def __repr__(self):  # pragma: nocover
        return self.__class__.__name__ + "({})".format(self.prop_name)


class Configuration:
    base_protocol: str
    base_host: str
    base_port: typing.Optional[int]
    media_path: PathType
    static_media_path: PathType
    static_media_url: str

    rss_feed_urls: str
    qr_cache_path: PathType

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

        extra_kwargs = kwargs.keys() - self.PROPERTIES

        if extra_kwargs:
            raise TypeError(
                f"Unexpected keyword arguments: {', '.join(sorted(extra_kwargs))}"
            )

        base_kwarg.update(kwargs)

        kwargs = base_kwarg

        self._base_dict = {}
        for kwarg in self.PROPERTIES.keys():
            value = kwargs[kwarg]
            setattr(self, kwarg, value)
            self._base_dict[kwarg] = value

        self.url_id = self.hash_encode(self.base_url)

        for kwarg in self.PROPERTIES.keys():
            setattr(self, kwarg, self.make_replacements(getattr(self, kwarg)))

        self.media_loc = FileLocation(
            self.media_path,
            self.static_media_url,
            self.static_media_path,
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

    @functools.cached_property
    def base_url(self) -> str:
        if self["base_port"] is None:
            base_url: str = self.base_host
        else:
            base_url = f"{self.base_host}:{self.base_port}"

        return f"{self.base_protocol}://{base_url}"

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
    **kwargs,
):
    """
    Initializes the configuration from config_loc or from the default
    configuration location.
    """

    config_location: typing.Union[pathlib.Path, None] = None
    if config_loc is not None:
        if not os.path.exists(config_loc):
            if config_loc_must_exist:
                raise MissingConfigError("Configuration location does not exist.")

            # Make sure we can write to this directory
            if not os.access(os.path.split(config_loc)[0], os.W_OK):
                msg = "Cannot write to {}".format(config_loc)
                raise ConfigWritePermissionsError(msg)
        config_location = pathlib.Path(config_loc)
    else:
        config_env_var = os.environ.get("AUDIO_FEEDER_CONFIG", None)
        falling_back = False
        if config_env_var is not None:
            config_location = pathlib.Path(config_env_var)
            if not config_location.exists():
                falling_back = True

        if falling_back or config_location is None:
            config_locs = [config_location] if config_location else []
            for config_location in config_locations(with_pwd=True):
                config_locs.append(config_location)
                if config_location.exists():
                    break
            else:
                config_location = None

        if falling_back:
            msg = (
                "Could not find config file from environment variable:"
                + " {},".format(os.environ["AUDIO_RSS_CONFIG"])
            )
            if config_location is not None:
                msg += f", using {config_location} instead."
            else:
                msg += ", using baseline configuration."

            warnings.warn(msg, RuntimeWarning)

    if config_location is not None and config_location.exists():
        new_conf = Configuration.from_file(config_location, **kwargs)
    else:
        if config_location is None:
            for config_location in config_locs:
                if not config_location.suffix == ".yml":
                    continue

                config_dir = config_location.parent
                if os.access(config_dir, os.W_OK):
                    break
            else:
                config_location = None

        new_conf = Configuration(config_loc_=config_location, **kwargs)

        if config_location is not None:
            logging.info("Creating configuration file at {}".format(config_location))

            new_conf.to_file(config_location)
    return new_conf


@functools.lru_cache(None)
def get_configuration() -> Configuration:
    """
    On first call, this loads the configuration object, on subsequent calls,
    this returns the original configuration object.
    """
    return init_config()


def read_from_config(field: str) -> typing.Any:
    """
    Convenience method for accessing specific fields from the configuration
    object.
    """
    return get_configuration()[field]


class MissingConfigError(ValueError):
    pass


class ConfigWritePermissionsError(ValueError):
    pass
