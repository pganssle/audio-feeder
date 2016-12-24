#!/usr/bin/env python3
from audio_rss_server.__version__ import VERSION

from setuptools import setup

DESCRIPTION = """
The audio-feeder provides a server that serves your audiobooks and other audio
content as RSS feeds, with rich metadata, and provides a web frontent for
navigation.
"""

setup(name="audio-feeder",
      version=VERSION,
      description=DESCRIPTION,
      author="Paul Ganssle",
      author_email="paul@ganssle.io",
      license="Apache 2.0",
      long_description=DESCRIPTION,
      packages=["audio_feeder"],
      zip_safe=True,
      requires=["Flask", "qrcode", "pillow", "jinja2", "pyyaml", 'requests'],
      install_requires=["Flask>=0.11.1"]
      classifiers=[
          'Development Status :: 1 - Planning',
          'Intended Audience :: Developers',
          'Framework :: Flask',
          'License :: OSI Approved :: Apache Software License',
          'Programming Language :: Python',
          'Programming Language :: Python :: 3 :: Only',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.5',
          'Programming Language :: Python :: 3.6',
      ])
