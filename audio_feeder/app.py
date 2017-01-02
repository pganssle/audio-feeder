#! /usr/bin/env python3
from flask import Flask
from .pages import root

def create_app(load_db=True, populate_qr_cache=True, progressbar=True):
    app = Flask(__name__)
    app.register_blueprint(root)

    # Now load the database if requested
    if load_db:
        from . import database_handler as dh
        dh.get_database()       # This loads the database into memory.

    if populate_qr_cache:
        if progressbar:
            from progressbar import ProgressBar, Bar, Timer, ETA
            pbar = ProgressBar(widgets=['Populating QR cache: ', Bar(),
                                        ' ', Timer(), ' ', ETA()])
            kwargs = {'pbar': pbar}
        else:
            kwargs = {}

        from .cache_utils import populate_qr_cache
        populate_qr_cache(**kwargs)

    return app
