"""Sphinx configuration for the audio-feeder documentation."""

import importlib.metadata

project = "audio-feeder"
author = "Paul Ganssle"
copyright = "2016-2026, Paul Ganssle"

version = release = importlib.metadata.version("audio_feeder")

extensions = [
    "sphinx.ext.intersphinx",
    "sphinx_click",
]

exclude_patterns = ["_build"]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

html_theme = "furo"
html_title = "audio-feeder"
html_static_path: list[str] = []
