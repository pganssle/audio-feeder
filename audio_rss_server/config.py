"""
Configuration manager - handles the application's global configuration.
"""
import os
import warnings

import yaml

CONFIG_LOCATIONS = [
    '~/.config/audio_rss_server/config.yml',
]

class Configuration:
    PROPERTIES = {
        'base_truncation_point': 500,
        'templates_base_loc': 'templates',
        'entry_templates_loc': 'entry_types',
        'RSS_templates_loc': 'RSS',
        'schema_loc': 'database/schema.yml',
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


def get_configuration(field=None):
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

    get_configuration._configuration = Configuration.from_file(config_location)

    if field is None:
        return get_configuration._configuration
    else:
        return get_configuration._configuration[field]


