"""
Configuration manager - handles the application's global configuration.
"""
import base64
import functools
import graphlib
import hashlib
import logging
import os
import pathlib
import re
import typing
import warnings
from itertools import product
from pathlib import Path

import attrs
import yaml

from . import cache_utils
from ._compat import Self
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


if typing.TYPE_CHECKING:

    class TemplatePath(Path):
        pass

else:

    class TemplatePath(type(Path())):  # type: ignore[misc]
        pass


class TemplateStr(str):
    pass


@typing.overload
def _path_converter(s: typing.Union[TemplatePath, TemplateStr]) -> TemplatePath:
    ...


@typing.overload
def _path_converter(s: typing.Union[str, Path]) -> Path:
    ...


def _path_converter(s):
    if isinstance(s, str):
        return Path(s)
    elif isinstance(s, TemplateStr):
        return TemplatePath(s)
    elif isinstance(s, (Path, TemplatePath)):
        return s
    else:
        raise TypeError(f"Wrong type for value: {type(s)}")


@attrs.define(slots=False)
class Configuration:
    config_location: Path
    base_truncation_point: int = 500
    templates_base_loc: Path = attrs.field(
        default=TemplatePath("{{CONFIG}}", "templates"), converter=_path_converter
    )
    entry_templates_loc: Path = attrs.field(
        default=TemplatePath("{{TEMPLATES}}", "entry_types"), converter=_path_converter
    )

    pages_templates_loc: Path = attrs.field(
        default=TemplatePath("{{TEMPLATES}}", "pages"), converter=_path_converter
    )

    rss_templates_loc: Path = attrs.field(
        default=TemplatePath("{{TEMPLATES}}", "rss"), converter=_path_converter
    )

    rss_entry_templates_loc: Path = attrs.field(
        default=TemplatePath("{{TEMPLATES}}", "rss/entry_types"),
        converter=_path_converter,
    )

    schema_loc: Path = Path("")  # Deprecated — this is unused
    database_loc: Path = attrs.field(
        default=TemplatePath("{{CONFIG}}", "database/db.sqlite"),
        converter=_path_converter,
    )

    static_media_path: Path = attrs.field(
        default=TemplatePath("{{CONFIG}}", "static"), converter=_path_converter
    )

    static_media_url: str = TemplateStr("{{URL}}/static")

    # If true, this will not inject the default CSS files.
    disable_default_css: bool = False

    # Relative to static
    media_path: str = "media"
    site_images_loc: str = "images/site-images"
    qr_cache_path: str = "images/qr_cache"
    cover_cache_path: str = "images/entry_cover_cache"
    media_cache_path: str = "media_cache"
    css_loc: str = "css"

    # Relative to base
    rss_feed_urls: str = "rss/{id}.xml"

    # Relative to others
    main_css_files: typing.Sequence[str] = ()  # Deprecated, no longer used
    extra_css_files: typing.Sequence[str] = ()
    thumb_max: typing.Tuple[int, int] = (200, 400)  # width, height
    base_protocol: str = "http"
    base_host: str = "localhost"
    base_port: typing.Optional[int] = 9090

    # API Keys
    google_api_key: typing.Optional[str] = None

    _ReplacementsMapType = typing.Mapping[str, str]
    REPLACEMENTS: typing.Final[_ReplacementsMapType] = {
        "{{CONFIG}}": "config_directory",
        "{{TEMPLATES}}": "templates_base_loc",
        "{{STATIC}}": "static_media_path",
        "{{URL}}": "base_url",
    }

    def __attrs_post_init__(self) -> None:
        self._attr_templates: typing.MutableMapping[
            str, typing.Union[TemplateStr, TemplatePath]
        ] = {}
        self._make_replacements()

    def __getitem__(self, key):
        return getattr(self, key)

    @functools.cached_property
    def base_url(self) -> str:
        if self.base_port is None:
            base_url: str = self.base_host
        else:
            base_url = f"{self.base_host}:{self.base_port}"

        return f"{self.base_protocol}://{base_url}"

    @functools.cached_property
    def config_directory(self) -> pathlib.Path:
        return self.config_location.parent

    @functools.cached_property
    def media_loc(self) -> FileLocation:
        return FileLocation(
            self.media_path, self.static_media_url, self.static_media_path
        )

    @functools.cached_property
    def url_id(self) -> str:
        return self.hash_encode(self.base_url)

    @classmethod
    def from_file(cls: typing.Type[Self], file_loc: Path, **kwargs) -> Self:
        if not file_loc.exists():
            raise IOError(f"File not found: {file_loc}")

        with open(file_loc, "r") as yf:
            config = yaml.safe_load(yf)

        template_types = {
            str: TemplateStr,
            Path: TemplatePath,
        }

        for field in attrs.fields(cls):
            if field.name not in config:
                continue

            if field.type in (str, Path):
                if re.search("{{[A-Z_]+}}", config[field.name]):
                    config[field.name] = template_types[field.type](config[field.name])

        config.update(kwargs)

        return cls(config_location=file_loc, **config)

    def to_file(self, file_loc: pathlib.Path) -> None:
        """
        Dumps the configuration to a YAML file in the specified location.

        This will not reflect any runtime modifications to the configuration
        object.
        """
        out_dict = {}

        for field in attrs.fields(self.__class__):
            if field.name in {"config_location", "schema_loc"}:
                # These ones don't get serialized
                continue
            if field.name in self._attr_templates:
                out_dict[field.name] = str(self._attr_templates[field.name])
                continue

            value = getattr(self, field.name)
            if isinstance(value, os.PathLike):
                value = os.fspath(value)
            elif isinstance(value, tuple):
                value = list(value)

            out_dict[field.name] = value

        with open(file_loc, "w") as yf:
            yaml.safe_dump(out_dict, stream=yf, default_flow_style=False)

    def hash_encode(self, str_data: str) -> str:
        """
        Encode some string data as a base64-encoded hash.

        This is not intended to be super robust, but it should work for the
        purposes of creating a reproducible number from input parameters.
        """
        h = hashlib.sha256()
        h.update(str_data.encode("utf-8"))

        return base64.b64encode(h.digest())[0:16].decode("utf-8")

    def to_dict(self):
        return attrs.to_dict(self)

    # Template replacement logic
    @functools.cached_property
    def _replacements(self) -> _ReplacementsMapType:
        def find_requirements(attr_name: str) -> typing.Sequence[str]:
            attr_value = getattr(self, attr_name)
            if isinstance(attr_value, TemplatePath):
                s = os.fspath(attr_value)
            elif isinstance(attr_value, TemplateStr):
                s = attr_value
            else:
                return ()

            return re.findall("{{[A-Z_]+}}", s)

        resolution_graph = {
            replacement: find_requirements(attr_name)
            for replacement, attr_name in self.REPLACEMENTS.items()
        }

        sort_order = graphlib.TopologicalSorter(resolution_graph).static_order()

        replacements_mapping: typing.MutableMapping[str, str] = {}
        for replacement_str in sort_order:
            attr_value = getattr(self, self.REPLACEMENTS[replacement_str])
            replaced_str = self._make_single_replacement(
                attr_value, replacements=replacements_mapping
            )

            replacements_mapping[replacement_str] = os.fspath(replaced_str)

        return replacements_mapping

    @typing.overload
    def _make_single_replacement(
        self, value: typing.Union[str, TemplateStr], replacements: _ReplacementsMapType
    ) -> str:
        ...

    @typing.overload
    def _make_single_replacement(
        self,
        value: typing.Union[Path, TemplatePath],
        replacements: _ReplacementsMapType,
    ) -> Path:
        ...

    def _make_single_replacement(self, value, replacements):
        if isinstance(value, TemplatePath):
            return Path(
                *(
                    self._make_single_replacement(
                        TemplateStr(component)
                        if component.startswith("{{")
                        else component,
                        replacements=replacements,
                    )
                    for component in value.parts
                )
            )
        elif isinstance(value, TemplateStr):
            out = str(value)
            for to_replace, replacement_value in replacements.items():
                out = out.replace(to_replace, replacement_value)

            if (m := re.search("{{([A-Z_]+)}}", out)) is not None:
                raise ValueError(f"Unknown replacement string: {m.groups()[0]}")

            return out
        else:
            return value

    def _make_replacements(self) -> None:

        replacements = self._replacements
        for field in attrs.fields(self.__class__):
            attrib = getattr(self, field.name)

            if isinstance(attrib, (TemplateStr, TemplatePath)):
                self._attr_templates[field.name] = attrib
                setattr(
                    self,
                    field.name,
                    self._make_single_replacement(attrib, replacements),
                )


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
                msg = f"Cannot write to {config_loc}"
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
                + f" {os.environ['AUDIO_RSS_CONFIG']},"
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
                raise ValueError("No valid configuration location found.")

        new_conf = Configuration(config_location, **kwargs)

        if config_location is not None:
            logging.info("Creating configuration file at %s", config_location)

            new_conf.to_file(config_location)
    return new_conf


@cache_utils.register_function_cache("config")
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
