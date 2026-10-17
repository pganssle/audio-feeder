Features
--------

- The directories that ``audio-feeder update`` and the ``/update`` page search for audiobooks can now be set with the new ``content_paths`` setting, e.g. ``content_paths: {books: [audiobooks, kids/audiobooks]}``. Paths are relative to the media directory, and symbolic links are followed. By default the whole media directory is searched, as the ``/update`` page already did. (`#11 <https://github.com/pganssle/audio-feeder/issues/11>`_)

- ``audio-feeder update`` no longer requires a path: with no arguments, it updates every directory in ``content_paths``. Passing a path still updates only that directory, and it can now also be an absolute path inside the media directory.
