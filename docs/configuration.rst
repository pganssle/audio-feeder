Configuration
=============

``audio-feeder`` is configured with a YAML file, ``config.yml``, which ``audio-feeder
install`` creates with every setting at its default value. Any setting that
isn't in the file takes its default, so you can delete the ones you don't need
to change, though a setting that ``audio-feeder`` doesn't recognize is an
error. A small configuration for a server on a home network might look like
this:

.. code-block:: yaml

    base_host: 192.168.1.20
    base_port: 9090
    google_api_key: AIza...
    metadata_retry:
      google_books:
        quota_cooldown: {hours: 6}

.. _config-location:

Where the configuration is found
--------------------------------

``audio-feeder`` reads a single configuration file, which is the first one
found in this order:

1. The file passed to the ``--config`` option of ``audio-feeder run``, which
   only that command has.
2. The file named by the ``AUDIO_FEEDER_CONFIG`` environment variable, if it's
   set and the file exists.
3. ``config.yml`` in the directory named by the ``AF_CONFIG_DIR`` environment
   variable, if it's set. In this case, none of the other directories are
   searched.
4. ``config.yml`` in the current directory, then in ``/etc/audio_feeder``,
   then in ``~/.config/audio_feeder``.

The files don't cascade, so the settings in a file found later in the list are
ignored rather than used as defaults. If no configuration file is found,
``audio-feeder`` writes one with the default settings to the first of these
directories that it can write to.

With the Docker configuration described in :doc:`installation`, the file is
``config/audio_feeder/config.yml`` in your checkout of ``audio_feeder_docker``,
which the container sees as ``/etc/audio_feeder/config.yml``.

Placeholders
------------

Settings that are paths or URLs can refer to some of the other settings with
these placeholders, which are replaced when the configuration is loaded:

``{{CONFIG}}``
    The directory containing the configuration file.

``{{TEMPLATES}}``
    The value of ``templates_base_loc``.

``{{STATIC}}``
    The value of ``static_media_path``.

``{{URL}}``
    The base URL, made from ``base_protocol``, ``base_host`` and
    ``base_port``, e.g. ``http://localhost:9090``.

The defaults use these so that the whole server directory can be moved around
and only ``config.yml`` needs to know where it is. Placeholders can refer to
settings that themselves use placeholders, as long as they don't form a
cycle.

Durations
---------

Most of the per-source settings under ``metadata_retry`` (see `Metadata`_)
are durations, which can be given either as a number of seconds or as a
mapping of the keyword arguments to :class:`datetime.timedelta`, i.e. any of
``weeks``, ``days``, ``hours``, ``minutes``, ``seconds``, ``milliseconds`` and
``microseconds``. For example, this sets the ``google_books`` source's
``quota_cooldown`` to 90 minutes:

.. code-block:: yaml

    metadata_retry:
      google_books:
        quota_cooldown: {hours: 1, minutes: 30}

Writing ``quota_cooldown: {minutes: 90}`` or ``quota_cooldown: 5400`` instead
would set the same duration.

When ``audio-feeder`` writes a configuration file, durations are written as a
number of seconds.

Server and URLs
---------------

``base_protocol``
    Default: ``http``

    The protocol of the base URL.

``base_host``
    Default: ``localhost``

    The host name or address of the server. ``audio-feeder run`` listens on
    this address, and it's also used to build the URLs in the feeds and QR
    codes, so it needs to be an address that your podcast app can reach; see
    :doc:`usage`.

``base_port``
    Default: ``9090``

    The port of the server. ``audio-feeder run`` listens on this port, and it's
    included in the base URL. If it's ``null``, the base URL has no port, which
    is what you want when the server is behind a web server on the protocol's
    default port; ``audio-feeder run`` then listens on Flask's default port,
    5000.

``static_media_url``
    Default: ``{{URL}}/static``

    The URL that the static files (everything in ``static_media_path``) are
    served from. Change this if your web server serves them from somewhere
    else, e.g. a different host.

``rss_feed_urls``
    Default: ``rss/{id}.xml``

    The URL of each book's feed, relative to the base URL. ``{id}`` is
    replaced with the ID of the entry; ``{table}`` (the name of the table the
    entry's data is in) and ``{tail}`` are also available. The app itself
    always serves the feeds at ``rss/<id>.xml``, so changing this only makes
    sense if something in front of the app rewrites the URLs to match.

Files and directories
---------------------

``static_media_path``
    Default: ``{{CONFIG}}/static``

    The directory of static files: the audio files themselves, the caches of
    covers, QR codes and rendered files, the CSS and the site's images and
    fonts. ``audio-feeder run`` serves this directory at a URL named after the
    directory (``/static`` for the default), which matches the default
    ``static_media_url``. When the app is run any other way, a web server has
    to serve it; see :ref:`deployment`.

``database_loc``
    Default: ``{{CONFIG}}/database/db.sqlite``

    The location of the database. A file ending in ``.sqlite`` or
    ``.sqlite3`` is an SQLite database; a file ending in ``.yml`` or
    ``.yaml``, or with no extension, uses the older YAML format. ``audio-feeder
    convert-db`` converts a YAML database to SQLite.

The following locations are relative to ``static_media_path`` on disk and to
``static_media_url`` in URLs.

``media_path``
    Default: ``media``

    The directory containing your books. See :doc:`usage` for how they should
    be laid out.

``media_cache_path``
    Default: ``media_cache``

    Where the files for the rendered feeds are generated (see :doc:`feeds`).
    These can take up a lot of space, and anything in here can be deleted, at
    the cost of regenerating it when the feed is next requested.

``cover_cache_path``
    Default: ``images/entry_cover_cache``

    Where book covers and their thumbnails are stored.

``qr_cache_path``
    Default: ``images/qr_cache``

    Where the QR code images for the feeds are stored, in a subdirectory for
    each base URL.

``site_images_loc``
    Default: ``images/site-images``

    The directory of images used by the site itself, e.g. ``default_cover.svg``,
    which is shown for books that don't have a cover.

``css_loc``
    Default: ``css``

    The directory of CSS files. The default stylesheets are copied here from
    the package the first time the book list is shown after the server
    starts.

.. _content-paths:

The directories that ``audio-feeder update`` and the ``/update`` page search
for content are relative to ``media_path``:

``content_paths``
    Default: ``{books: [.]}``

    A mapping from each type of content to the directories that contain it.
    At the moment the only type of content is ``books``, and any other key
    makes the update fail. Each type can have a list of directories, a single
    directory, or nothing (``null`` or an empty list), in which case that type
    isn't updated. The default searches the whole media directory:

    .. code-block:: yaml

        content_paths:
          books:
          - .

    To only search some directories, list them under ``books``:

    .. code-block:: yaml

        content_paths:
          books:
          - audiobooks
          - kids/audiobooks

    The directories can also be absolute paths, but either way they must be
    inside the media directory, since the paths in the database are stored
    relative to it. Symbolic links are followed, though, so to add a directory
    from elsewhere, link to it from the media directory. A book that is found
    in more than one of the directories (e.g. because one is inside another)
    is only added once.

Appearance
----------

``base_truncation_point``
    Default: ``500``

    Roughly how many characters of a book's description to show in the book
    list before hiding the rest behind a "Read More" link. The cut is moved
    forward to the end of the word it falls in, and descriptions that are no
    longer than this are shown in full.

``thumb_max``
    Default: ``[200, 400]``

    The maximum width and height, in pixels, of the cover thumbnails shown in
    the book list. Covers are scaled down, keeping their aspect ratio, to fit
    within these, and they are never scaled up. A ``0`` or ``null`` means that
    dimension isn't limited. Changing this isn't applied to thumbnails that
    already exist.

``extra_css_files``
    Default: ``[]``

    A list of additional CSS files to include in the page, as paths relative to
    ``css_loc``. They are included after the default stylesheets, so they can
    override them.

``disable_default_css``
    Default: ``false``

    If true, the default stylesheets aren't included in the page, and only
    ``extra_css_files`` are.

Templates
---------

The web page and the feeds are rendered from `Jinja <https://jinja.palletsprojects.com/>`_
templates. The defaults are part of the package (in
``audio_feeder/data/templates``), and each of these settings is a directory in
which you can put your own versions to override them. None of these
directories are created by ``audio-feeder install``, and when a template isn't
found in them, the default is used.

``templates_base_loc``
    Default: ``{{CONFIG}}/templates``

    The base directory of the template overrides, which the other template
    settings refer to as ``{{TEMPLATES}}``.

``pages_templates_loc``
    Default: ``{{TEMPLATES}}/pages``

    The directory to look for ``list.tpl``, the template of the book list
    page, in.

``rss_templates_loc``
    Default: ``{{TEMPLATES}}/rss``

    The directory to look for ``rss_feed.tpl``, the template of the RSS feeds,
    in.

``entry_templates_loc``
    Default: ``{{TEMPLATES}}/entry_types``

    The directory of templates for each entry in the book list, with a
    subdirectory for each type of entry (e.g. ``Book``) containing a template
    for each field (``name.tpl``, ``author.tpl`` and ``description.tpl``).
    If the subdirectory for a type exists, the templates in it are used
    instead of all of the defaults for that type.

``rss_entry_templates_loc``
    Default: ``{{TEMPLATES}}/rss/entry_types``

    Like ``entry_templates_loc``, but for the entries in the RSS feeds.

Metadata
--------

``google_api_key``
    Default: ``null``

    A `Google Books API key
    <https://developers.google.com/books/docs/v1/using#APIKey>`_ to use when
    looking up books. Without one, requests are made anonymously, which Google
    limits more strictly.

``metadata_retry``
    Default: ``{}``

    When to retry looking up metadata after failures, as a mapping from the
    name of each metadata source to its settings. Currently the only source is
    ``google_books``. Sources without an entry, and settings that aren't
    specified for a source, use the defaults below. For example:

    .. code-block:: yaml

        metadata_retry:
          google_books:
            quota_cooldown: {hours: 6}
            request_timeout: 10

    The settings for each source are:

    ``not_found_retry_base``
        Default: 1 day

        When a source has nothing for a book (or rejects the query), wait this
        long before asking again, doubling with each consecutive failure.
        Changing the information used to look up the book (e.g. fixing a typo
        in the title) resets this.

    ``not_found_retry_max``
        Default: 32 days

        The longest to wait before retrying a book.

    ``quota_cooldown``
        Default: 1 hour

        How long to stop querying a source after its quota is exhausted. Books
        that weren't looked up are retried on the next update after that.

    ``unavailable_cooldown``
        Default: 5 minutes

        How long to stop querying a source after network or server errors.

    ``request_retries``
        Default: ``3``

        How many times to retry a request after a per-minute rate limit or a
        server error, before treating the source as unavailable.

    ``request_retry_base``
        Default: 2 seconds

        The delay before retrying a request, doubling with each retry (with
        random jitter).

    ``request_retry_max``
        Default: 30 seconds

        The longest to wait before retrying a request. If the source asks for
        a longer wait than this, it's treated as unavailable instead.

    ``request_timeout``
        Default: 30 seconds

        How long to wait for a response to a request.

    All of these except ``request_retries`` are durations, in the format
    described in `Durations`_.

Deprecated settings
-------------------

These are still accepted, so that old configuration files keep working, but
they have no effect.

``schema_loc``
    Unused, and not written to new configuration files.

``main_css_files``
    No longer used; the default stylesheets are found automatically, and
    ``disable_default_css`` turns them off.
