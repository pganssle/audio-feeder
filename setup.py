#!/usr/bin/env python3
from audio_feeder.__version__ import VERSION

from setuptools import setup, find_packages
import itertools
import os

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
    'click>=6.0',
    'progressbar2',
    'lxml>=2.0'
]

DATA_DIR = 'audio_feeder/data'
DATA_FILES = [os.path.relpath(os.path.join(cdir, fname), 'audio_feeder')
    for cdir, dirs, fnames in os.walk(DATA_DIR)
    for fname in fnames
]

setup(name="audio-feeder",
      version=VERSION,
      description=DESCRIPTION,
      author="Paul Ganssle",
      author_email="paul@ganssle.io",
      license="Apache 2.0",
      long_description=DESCRIPTION,
      packages=find_packages(),
      package_data={'audio_feeder': DATA_FILES},
      include_package_data=True,
      zip_safe=True,
      setup_requires=['pytest-runner'],
      install_requires=INSTALL_REQUIREMENTS,
      tests_require=['pytest>=3.0'],
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
