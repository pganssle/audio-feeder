#! /usr/bin/env python3
from flask import Flask
from .pages import root

import os
import logging as log

def create_app(load_db=True, populate_qr_cache=True, progressbar=False):
    # Set up logging
    log_level = os.environ.get('AF_LOGGING_LEVEL', None)
    if log_level is not None:
        log_levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        if log_level.upper() in log_levels:
            log_level = getattr(log, log_level)

            log.basicConfig(level=log_level)
        else:
            log.warning('Invalid log level: {}'.format(log_level.upper()))
    else:
        log.warning('No log level set, using default level.')

    log.info('Creating Flask application')
    app = Flask(__name__)
    app.register_blueprint(root)

    # Now load the database if requested
    if load_db:
        from . import database_handler as dh
        log.info('Loading database.')
        dh.get_database()       # This loads the database into memory.
        log.info('Database loaded.')

    if populate_qr_cache:
        if progressbar:
            from progressbar import ProgressBar, Bar, Timer, ETA
            pbar = ProgressBar(widgets=['Populating QR cache: ', Bar(),
                                        ' ', Timer(), ' ', ETA()])
            kwargs = {'pbar': pbar}
        else:
            log.info('Populating QR cache.')
            kwargs = {}

        from .cache_utils import populate_qr_cache
        populate_qr_cache(**kwargs)

    return app
