"""
Configuration manager - handles the application's global configuration.
"""
from itertools import product
import os
import logging
import warnings

import yaml
from collections import OrderedDict

CONFIG_DIRS = [os.path.expanduser(x) for x in (
    '~/.config/audio_feeder/', 
)]

CONFIG_NAMES = ['config.yml']
CONFIG_LOCATIONS = list(
    os.path.join(bdir, cfile)
    for bdir, cfile in product(CONFIG_DIRS, CONFIG_NAMES)
)

class _ConfigProperty:
    def __init__(self, prop_name):
        self.prop_name = prop_name

    def __repr__(self):
        return self.__class__.__name__ + '({})'.format(self.prop_name)

class Configuration:
    PROPERTIES = OrderedDict((
        ('base_truncation_point', 500),
        ('templates_base_loc', '{{CONFIG}}/templates'),
        ('entry_templates_loc', '{{TEMPLATES}}/entry_types'),
        ('pages_templates_loc', '{{TEMPLATES}}/pages'),
        ('rss_templates_loc', '{{TEMPLATES}}/rss'),
        ('rss_entry_templates_loc', '{{TEMPLATES}}/rss/entry_types'),
        ('schema_loc', '{{CONFIG}}/database/schema.yml'),
        ('database_loc', '{{CONFIG}}/database/db'),
        ('static_media_path', '{{CONFIG}}/static'),
        ('static_media_url', '{{URL}}/static'),
        ('base_media_path', '{{STATIC}}/media'),
        ('base_media_url', '{{URL}}/static/media'),
        ('site_images_loc', 'images/site-images'),
        ('qr_cache_path', 'images/qr_cache'),
        ('cover_cache_path', 'images/entry_cover_cache'),
        ('rss_feed_urls', 'rss/{id}.xml'),
        ('css_loc', 'css'),
        ('main_css_files', ['main.css']),
        ('thumb_max', [200, 500]),   # width, height
        ('base_host', 'localhost'),
        ('base_port', 9090),
    ))

    REPLACEMENTS = {
        '{{CONFIG}}': _ConfigProperty('config_directory'),
        '{{TEMPLATES}}': _ConfigProperty('templates_base_loc'),
        '{{STATIC}}': _ConfigProperty('static_media_path'),
        '{{URL}}': _ConfigProperty('base_url')
    }

    def __init__(self, config_loc_=None, **kwargs):
        if config_loc_ is None:
            # If configuration location is not specified, we'll use pwd.
            config_loc = os.path.join(os.getcwd(), 'config.yml')

        self.config_location = config_loc_
        self.config_directory = os.path.split(self.config_location)[0]

        base_kwarg = self.PROPERTIES.copy()

        for kwarg in kwargs.keys():
            if kwarg not in self.PROPERTIES:
                raise TypeError('Unexpected keyword argument: {}'.format(kwarg))

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
            self.base_url = '{}:{}'.format(self.base_host, self.base_port)

        for kwarg in self.PROPERTIES.keys():
            setattr(self, kwarg, self.make_replacements(getattr(self, kwarg)))

    @classmethod
    def from_file(cls, file_loc, **kwargs):
        if not os.path.exists(file_loc):
            raise IOError('File not found: {}'.format(file_loc))

        with open(file_loc, 'r') as yf:
            config = yaml.safe_load(yf)

        config.update(kwargs)

        return cls(config_loc_=file_loc, **config)

    def to_file(self, file_loc):
        """
        Dumps the configuration to a YAML file in the specified location.

        This will not reflect any runtime modifications to the configuration
        object.
        """
        with open(file_loc, 'w') as yf:
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

    def make_replacements(self, value):
        if not isinstance(value, str):
            return value

        for k, repl in self.REPLACEMENTS.items():
            if k not in value:
                continue

            if isinstance(repl, _ConfigProperty):
                return value.replace(k, self.get(repl.prop_name))
            else:
                return value.replace(k, repl)

        return value

    def to_dict(self):
        return dict(*self.items())


def init_config(config_loc=None, config_loc_must_exist=False, **kwargs):
    """
    Initializes the configuration from config_loc or from the default
    configuration location.
    """

    config_locations = []
    found_config = False
    if config_loc is not None:
        if not os.path.exists(config_loc):
            if config_loc_must_exist:
               raise MissingConfigError('Configuration location does not exist.')

            # Make sure we can write to this directory
            if not os.access(os.path.split(config_loc)[0], os.W_OK):
                msg = 'Cannot write to {}'.format(config_loc)
                raise ConfigWritePermissionsError(msg)

        config_location = config_loc
        found_config = True

    if not found_config:
        config_location = os.environ.get('AUDIO_FEEDER_CONFIG', None)
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
            msg = ('Could not find config file from environment variable:' +
                   ' {},'.format(os.environ['AUDIO_RSS_CONFIG']))
            if found_config:
                msg += ', using {} instead.'.format(config_location)
            else:
                msg += ', using baseline configuration.'

            warnings.warn(msg, RuntimeWarning)

    if found_config and os.path.exists(config_location):
        new_conf = Configuration.from_file(config_location, **kwargs)
        get_configuration._configuration = new_conf
    else:
        if not found_config:
            for config_location in config_locs:
                if not config_location.endswith('.yml'):
                    continue

                config_dir = os.path.split(config_location)[0]
                if os.access(config_dir, os.W_OK):
                    break
            else:
                config_location = None

        new_conf = Configuration(config_loc_=config_location, **kwargs)
        get_configuration._configuration = new_conf

        if config_location is not None:
            logging.info('Creating configuration file at {}'.format(config_location))

            get_configuration._configuration.to_file(config_location)


def get_configuration():
    """
    On first call, this loads the configuration object, on subsequent calls,
    this returns the original configuration object.
    """
    config_obj = getattr(get_configuration, '_configuration', None)
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