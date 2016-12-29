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
    from . import database_handler as dh

    if content_type in ('b', 'books'):
        updater = dh.BookDatabaseUpdater(path)
    else:
        raise ValueError('Unknown type {}'.format(utype))

    db = dh.load_database()
    updater.update_db(db)
    dh.save_database(db)

