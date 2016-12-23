"""
Configuration manager - handles the application's global configuration.
"""
import os
import warnings

import yaml

CONFIG_LOCATIONS = [
    os.path.expanduser('~/.config/audio_rss_server/config.yml'),
]

class Configuration:
    PROPERTIES = {
        'base_truncation_point': 500,
        'templates_base_loc': 'templates',
        'entry_templates_loc': 'entry_types',
        'RSS_templates_loc': 'RSS',
        'schema_loc': 'database/schema.yml',
        'database_loc': 'database/db',
        'static_media_path': 'static/',
        'rss_feed_urls': 'rss/{id}.xml',
        'qr_cache_path': 'qr_cache/'
    }
    def __init__(self, **kwargs):
        base_kwarg = self.PROPERTIES.copy()

        for kwarg in kwargs.keys():
            if kwarg not in PROPERTIES:
                raise TypeError('Unexpected keyword argument: {}'.format(kwarg))

        base_kwarg.update(kwargs)

        kwargs = base_kwarg

        for kwarg, value in kwargs.items():
            setattr(self, kwarg, value)

    @classmethod
    def from_file(cls, file_loc):
        if not os.path.exists(file_loc):
            raise IOError('File not found: {}'.format(file_loc))

        with open(file_loc, 'r') as yf:
            config = yaml.safe_load(yf)
        
        return cls(**config)

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default):
        return getattr(self, key, default)


def get_configuration():
    """
    On first call, this loads the configuration object, on subsequent calls,
    this returns the original configuration object.
    """
    config_obj = getattr(get_configuration, '_configuration', None)
    if config_obj is not None:
        return config_obj

    config_location = os.environ.get('AUDIO_RSS_CONFIG', None)
    falling_back = False
    found_config = False
    if config_location is not None:
        if not os.path.exists(config_location):
            falling_back = True
        else:
            found_config = True

    if not found_config:
        for config_location in CONFIG_LOCATIONS:
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

    if found_config:
        get_configuration._configuration = Configuration.from_file(config_location)
    else:
        get_configuration._configuration = Configuration()

    return get_configuration._configuration


def read_from_config(field):
    """
    Convenience method for accessing specific fields from the configuration
    object.
    """
    return get_configuration()[field]


