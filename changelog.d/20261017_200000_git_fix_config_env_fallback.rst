Bugfixes
--------

- Fixed a crash when the ``AUDIO_FEEDER_CONFIG`` environment variable points to a configuration file that doesn't exist. audio-feeder now warns and falls back to the other configuration locations (or the baseline configuration), as intended. (`#103 <https://github.com/pganssle/audio-feeder/issues/103>`_)
