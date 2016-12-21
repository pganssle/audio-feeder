#!/usr/bin/env python3
from audio_rss_server.__version__ import VERSION

from setuptools import setup

DESCRIPTION = """
The audio-rss-server provides a server that serves your 
"""

setup(name="audio-rss-server",
      version=VERSION,
      description="Extensions to the standard Python datetime module",
      author="Paul Ganssle",
      author_email="paul@ganssle.io",
      license="Apache 2.0",
      long_description="""
The dateutil module provides powerful extensions to the
datetime module available in the Python standard library.
""",
      packages=["audio_rss_server"],
      zip_safe=True,
      requires=["Flask", "qrcode", "pillow", "jinja2", "pyyaml"],
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
