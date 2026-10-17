Bugfixes
--------

- ``audio-feeder install --config-dir DIR`` now puts the database and static directories in ``DIR`` when it's run from another directory. Previously it wrote ``DIR/config.yml``, but then created a second ``config.yml``, ``static/`` and ``database/`` in the current directory. ``DIR`` is also created if it doesn't exist, rather than failing with ``ConfigWritePermissionsError``. (`#106 <https://github.com/pganssle/audio-feeder/issues/106>`_)
