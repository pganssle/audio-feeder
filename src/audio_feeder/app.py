#! /usr/bin/env python3
import logging as log
import os
import threading

from flask import Flask

from . import cache_utils
from . import database_handler as dh
from . import resources
from .config import read_from_config
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
    log_level_env = os.environ.get("AF_LOGGING_LEVEL", None)
    log_level = None
    warnings = []
    if log_level_env is not None:
        log_level_env = log_level_env.upper()
        log_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        if log_level_env in log_levels:
            log_level = getattr(log, log_level_env)
        else:
            warnings.append(("Invalid log level: %s", log_level_env))
    if log_level is None:
        warnings.append(("No log level set, using INFO",))
        log_level = log.INFO

    log.basicConfig(
        level=log_level,
        format="%(levelname)s: [%(asctime)s] %(name)s:"
        + "%(filename)s:%(lineno)d (%(threadName)s) %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S%z",
    )
    for warning in warnings:
        log.warning(*warning)

    log.info("Refreshing fonts on disk")
    static_media_path = read_from_config("static_media_path")
    resources.update_resource(
        "audio_feeder.data.site.fonts", static_media_path / "fonts"
    )

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
