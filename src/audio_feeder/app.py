#! /usr/bin/env python3
import logging as log
import os
import threading

from flask import Flask

from . import cache_utils
from . import database_handler as dh
from .pages import root


def warm_caches(load_db=True, populate_qr_cache=True, progressbar=False):
    log.info("Warming caches in a background thread")
    if load_db:
        log.info("Loading database.")
        dh.get_database()  # This loads the database into memory.
        log.info("Database loaded.")

    if populate_qr_cache:
        if progressbar:
            from progressbar import ETA, Bar, ProgressBar, Timer

            pbar = ProgressBar(
                widgets=["Populating QR cache: ", Bar(), " ", Timer(), " ", ETA()]
            )
            kwargs = {"pbar": pbar}
        else:
            log.info("Populating QR cache.")
            kwargs = {}

        cache_utils.populate_qr_cache(**kwargs)


def create_app(load_db=True, populate_qr_cache=True, progressbar=False, block=False):
    # Set up logging
    log_level = os.environ.get("AF_LOGGING_LEVEL", None)
    if log_level is not None:
        log_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        if log_level.upper() in log_levels:
            log_level = getattr(log, log_level)

            log.basicConfig(level=log_level)
        else:
            log.warning("Invalid log level: {}".format(log_level.upper()))
    else:
        log.warning("No log level set, using default level.")

    log.info("Creating Flask application")
    app = Flask(__name__)
    app.register_blueprint(root)

    # Now load the database and populate the QR cache in a background thread
    # if requested.
    kwargs = dict(
        load_db=load_db, populate_qr_cache=populate_qr_cache, progressbar=progressbar
    )

    background_thread = threading.Thread(
        target=warm_caches, daemon=not block, kwargs=kwargs
    )
    background_thread.start()

    return app
