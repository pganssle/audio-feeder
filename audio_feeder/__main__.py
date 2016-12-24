#! /usr/bin/env python3
DESCRIPTION = """This is the main script that runs the audio_feeder backend.
"""
from flask import Flask

app = Flask('audio_feeder')

@app.route('/')
def main_index():
    pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=DESCRIPTION)

    parser.add_argument('-h', '--host', type=str, default='0.0.0.0',
        help='The host to run the application on.')

    parser.add_argument('-p', '--port', type=int, default=9090,
        help='The port to run the application on.')

    args = parser.parse_args()

    app.run(host=args.host, port=args.port)
