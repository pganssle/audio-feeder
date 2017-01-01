#! /usr/bin/env python3
from flask import Flask
from .pages import root

def create_app(load_db=True):
    app = Flask(__name__)
    app.register_blueprint(root)

    # Now load the database if requested
    if load_db:
        from . import database_handler as dh
        dh.get_database()       # This loads the database into memory.

    return app
