"""
Command line scripts
"""
import click

@click.group()
def cli():
    """
    Options are:
        run
        update
    """
    pass

@cli.command()
@click.option('--host', default='localhost',
    help='The host to run the application on.')
@click.option('-p', '--port', default=9090, type=int,
    help='The port to run the application on.')
@click.option('-c', '--config', default=None, type=str,
    help='A YAML config file to use for this particular run.')
def run(host, port, config):
    """
    Runs the flask application, starting the web page with certain configuration
    options specified.
    """
    from .__main__ import app
    from .config import read_from_config, init_config

    init_config(config_loc=config, base_host=host, base_port=port)

    app.static_folder = read_from_config('static_media_path')

    app.run(host=host, port=port)


@cli.command()
@click.option('-t', '--content-type', type=str, default='books',
    help=('The type of content to load from the directories. Options:' +
          '  b / books: Audiobooks'))
@click.argument('path', metavar='PATH', type=str, required=True)
def update(content_type, path):
    """
    Add a specific path to the databases, loading all content and updating the
    database where necessary.

    The path at PATH will be recursively searched for data.
    """
    import os

    from .config import read_from_config

    from . import database_handler as dh

    # If this is a relative path, interpret it as relative to the base
    # media path, not the cwd.
    path = os.path.join(read_from_config('base_media_path'), path)

    if content_type in ('b', 'books'):
        updater = dh.BookDatabaseUpdater(path)
    else:
        raise ValueError('Unknown type {}'.format(utype))

    db = dh.load_database()
    updater.update_db(db)
    dh.save_database(db)


@cli.command()
@click.option('-c', '--config-dir', type=str, default=None,
    help=('The configuration directory to use as a base for all'))
@click.option('-n', '--config-name', type=str, default=None,
    help='The name to use for the configuration file. Default is config.yml')
def install(config_dir, config_name):
    """
    Installs the feeder configuration and populates the initial file structures
    with the default package data.
    """
    import os
    import shutil
    import warnings

    from pkg_resources import resource_filename, cleanup_resources

    from . import config

    # Assign a configuration directory
    if config_dir is None:
        for config_dir in config.CONFIG_DIRS:
            if not os.path.exists(config_dir):
                try:
                    os.makedirs(config_dir)
                    break
                except Exception as e:
                    warnings.warn('Failed to make directory {}'.format(config_dir),
                        RuntimeWarning)
            else:
                break
        else:
            raise IOError('Failed to create any configuration directories.')

    config_name = config_name or config.CONFIG_NAMES[0]
    config_loc = os.path.join(config_dir, config_name)

    # Initialize the configuration
    config.init_config(config_loc)
    config_obj = config.get_configuration()

    # Write the configuration to file
    config_obj.to_file(config_loc)

    # Create the directories that need to exist, if they don't already
    make_dir_entries = (
        'templates_base_loc',
        'entry_templates_loc',
        'pages_templates_loc',
        'rss_templates_loc',
        'rss_entry_templates_loc',
        'database_loc',
        'static_media_path',
    )   # Absolute paths

    make_dir_directories = [config_obj[x] for x in make_dir_entries]
    static_paths = [
        os.path.join(config_obj['static_media_path'], config_obj[x])
        for x in ('site_images_loc', 'css_loc',
                  'cover_cache_path', 'qr_cache_path')
    ]   # Relative paths

    (site_images_path, css_path,
     cover_cache_path, qr_cache_path) = static_paths

    make_dir_directories += static_paths

    for cdir in make_dir_directories:
        if not os.path.exists(cdir):
            os.makedirs(cdir)

    # Load package data if it doesn't already exist.
    pkg_name = 'audio_feeder'
    
    # Schema
    if not os.path.exists(config_obj['schema_loc']):
        sl_fname = resource_filename(pkg_name, 'data/database/schema.yml')
        shutil.copy2(sl_fname, config_obj['schema_loc'])

    css_files = [os.path.join(css_path, fname)
                 for fname in config_obj['main_css_files']]

    # CSS files
    for css_fname, css_file in zip(config_obj['main_css_files'], css_files):
        if not os.path.exists(css_file):
            c_fname = resource_filename(pkg_name,
                                        os.path.join('data/site/css', css_fname))

            shutil.copy2(c_fname, css_file)

    # Directories
    pkg_dir_map = {
        'entry_templates_loc': 'data/templates/entry_types',
        'pages_templates_loc': 'data/templates/pages',
        'rss_templates_loc': 'data/templates/rss',
        'rss_entry_templates_loc': 'data/templates/rss/entry_types',
    }

    pkg_dir_map = {config_obj[k]: v for k, v in pkg_dir_map.items()}
    pkg_dir_map.update({
        k: v for k, v in zip(static_paths[:-1], ['data/site/site-images',
                                                 'data/site/css'])
    })

    # This may duplicate some files if entries nested in the original package
    # are not nested in the installed configuration.
    src_locs = set(pkg_dir_map.values())
    for dst_dir, pkgdata_loc in pkg_dir_map.items():
        pkgdata_fname = resource_filename(pkg_name, pkgdata_loc)
        for base_dir, dirs, fnames in os.walk(pkgdata_fname):
            for fname in fnames:
                src_path = os.path.join(base_dir, fname)
                rel_path = os.path.relpath(src_path, pkgdata_fname)

                dst_path = os.path.join(dst_dir, rel_path)

                if not os.path.exists(dst_path):
                    dst_subdir = os.path.split(dst_path)[0]
                    if not os.path.exists(dst_subdir):
                        os.makedirs(dst_subdir)

                    shutil.copy2(src_path, dst_path)
