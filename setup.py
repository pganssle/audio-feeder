#!/usr/bin/env python3
from audio_feeder.__version__ import VERSION

from setuptools import setup

DESCRIPTION = """
The audio-feeder provides a server that serves your audiobooks and other audio
content as RSS feeds, with rich metadata, and provides a web frontent for
navigation.
"""

INSTALL_REQUIREMENTS = [
    'Flask>=0.11.1',
    'ruamel.yaml>=0.13.4',
    'qrcode>=5.3',
    'Pillow>=3.4.2',
    'requests>=2.12.4',
    'jinja2',
    'click>=6.0'
]

setup(name="audio-feeder",
      version=VERSION,
      description=DESCRIPTION,
      author="Paul Ganssle",
      author_email="paul@ganssle.io",
      license="Apache 2.0",
      long_description=DESCRIPTION,
      packages=["audio_feeder"],
      zip_safe=True,
      install_requires=INSTALL_REQUIREMENTS,
      entry_points={
        'console_scripts': [
            'audio-feeder=audio_feeder.cli:cli'
        ]
      },
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
