Features
--------

- When looking up metadata from Google Books, audio-feeder now stops making requests for a while after hitting the API's usage limits, or after repeated network or server errors, rather than continuing to make requests that will fail. Books that couldn't be looked up are retried on a later update.

- Books that Google Books has no match for are now retried with increasing delays (starting at a day, up to about a month), rather than on every update. Changing a book's title, authors or identifiers makes it eligible to be retried right away.

- The delays before retrying after these failures can be changed with the new ``metadata_retry`` setting, e.g. ``metadata_retry: {google_books: {quota_cooldown: {hours: 6}}}``. Durations are given in seconds, or as a mapping like ``{days: 1}``.

Bugfixes
--------

- Fixed an issue where a book's Google Books description would not be saved if an earlier attempt to look up the book had failed. Books affected by this will have their descriptions retrieved on the next update.

- Fixed file metadata not being preserved when saving and loading the YAML database.

Misc
----

- The SQLite database schema version is now 3. Databases are upgraded automatically, and a copy of the database from before the upgrade is saved next to it (e.g. ``db.sqlite.v2.bak``). Older versions of audio-feeder will not be able to open an upgraded database.
