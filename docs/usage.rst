Setting up a library
====================

Once you've installed ``audio-feeder`` (see :doc:`installation`), getting to a
running server takes three steps: create a configuration directory with
``audio-feeder install``, put your books in its media directory, and load them
into the database with ``audio-feeder update``. After that, ``audio-feeder
run`` starts the server.

If you're using the Docker configuration, the installation steps in
:doc:`installation` already take care of most of this: ``install_audio_feeder.sh``
creates the configuration directory at ``/etc/audio_feeder`` in the container,
your audiobooks are mounted in its media directory, and the container runs the
server. The rest of this page is still worth reading for how to lay out and
name your books (see `Adding books`_) and for what the update does, but run the
commands in the container, e.g. ``docker-compose run audio_feeder audio-feeder
update``, and skip `Running the server`_ and `Deploying it`_.

Creating the configuration directory
------------------------------------

``audio-feeder install`` creates a configuration directory with a default
``config.yml``, the directories that the server needs and the static files that
the web page uses (its stylesheets, themes and images):

.. code-block:: console

    $ audio-feeder install --config-dir ~/audiobook_server

Without ``--config-dir``, it uses the directory in the ``AF_CONFIG_DIR``
environment variable if that's set, and otherwise the first of
``/etc/audio_feeder`` and ``~/.config/audio_feeder`` that either exists or can
be created. With the default settings, the result looks like this:

.. code-block:: text

    ~/audiobook_server/
    ├── config.yml
    ├── database/
    └── static/
        ├── images/
        │   ├── entry_cover_cache/
        │   ├── qr_cache/
        │   └── site-images/
        └── media_cache/

You can run ``audio-feeder install`` again on an existing directory, e.g. after
upgrading, to update the static files. This also rewrites ``config.yml`` with
every setting in it, which keeps the values you've set but not any comments.
The settings in ``config.yml`` are described in :doc:`configuration`; the defaults are fine for trying it out on
the computer you installed it on, but you'll probably want to at least set
``base_host`` to something your phone can reach.

Commands that need the configuration find it by looking for ``config.yml`` in
the current directory, then in ``/etc/audio_feeder``, then in
``~/.config/audio_feeder``, so the simplest thing to do is to run them from the
configuration directory. See :ref:`config-location` for the other ways to point
them at it.

Adding books
------------

Books go in the media directory, which is ``static/media`` in the
configuration directory by default. You can copy them there, or make
``static/media`` a symlink or bind mount of wherever your audiobooks already
live.

Each book is a directory containing its audio files, which are any files with
the extensions ``.mp3``, ``.mp4``, ``.m4a``, ``.m4b``, ``.aac``, ``.ac3`` or
``.ogg``. The files are put in the feed in "natural" sort order, so that
``Part 2.mp3`` comes before ``Part 10.mp3``. Any directory that directly
contains an audio file is treated as a book, and its subdirectories aren't
searched; any other directory is searched for books recursively, so you can
organize the books into folders however you like. The folders show up in the
web page's :ref:`folder tree <folders>`.

The name of each book's directory gives its authors and title, in one of these
formats::

    Author - Title
    Author - [Series Name 2] - Title

Multiple authors can be separated by ``&``, ``and`` or a comma, e.g. ``Neil
Gaiman & Terry Pratchett - Good Omens``. For example, a media directory might
look like this:

.. code-block:: text

    static/media/
    └── audiobooks/
        ├── Fiction/
        │   ├── Bram Stoker - Dracula/
        │   ├── Louisa May Alcott - [Little Women 01] - Little Women/
        │   └── Louisa May Alcott - [Little Women 02] - Little Men/
        └── Nonfiction/
            └── Edith Wharton - The Writing of Fiction/

A book directory whose name doesn't match one of these formats is still added,
but with the whole directory name as its title and no author, and the update
logs a warning naming the directory. Its metadata is still looked up from
Google Books by title alone, but the author is never filled in from that
search, since it may well have matched a different book. To give the book an
author, rename the directory and update again.

If the directory contains an image (a ``.png``, ``.jpg``, ``.svg``, ``.gif``,
``.tif`` or ``.bmp`` file), it's used as the book's cover, preferring a file
whose name starts with "cover". Otherwise the cover comes from Google Books, if it
has one.

Updating the database
---------------------

``audio-feeder update`` searches the media directory for books, adds new ones
to the database, removes the ones that no longer exist, and looks up the
metadata of any books that don't have it yet:

.. code-block:: console

    $ audio-feeder update

By default, the whole media directory is searched. If only some of it contains
books, list those directories in the :ref:`content_paths <content-paths>`
setting, e.g.:

.. code-block:: yaml

    content_paths:
      books:
      - audiobooks
      - kids/audiobooks

The directories are relative to the media directory and have to be inside it,
but symbolic links are followed, so you can add a directory from elsewhere by
linking to it from the media directory. To update a single directory instead
of the configured ones, pass it to the command, e.g. ``audio-feeder update
audiobooks/Fiction``.

The first update of a large library can take a while, since it has to hash and read
the metadata of every audio file and look up every book on Google Books. Later
updates skip the files of books that are already in the database, which means
that changes to an existing book's files aren't noticed unless you pass
``--check-hashes``; this re-hashes the files of every book and re-reads the
metadata of the ones that changed. ``--reload-metadata`` looks up every book
on Google Books again, even the ones that already have metadata.

You can also start an update from the browser by visiting the ``/update`` URL
of a running server, which updates the directories in ``content_paths`` and shows the
progress at ``/update_status`` until it's done. It takes the same options as
the command, as query parameters: ``/update?reloadMetadata=true`` reloads the
metadata of every book, and ``/update?checkHashes=true`` re-checks the hashes
of the files that are already in the database.

Books that Google Books has no match for are retried on later updates, with
increasing delays between attempts. If one never matches, ``audio-feeder
find-missing-books load`` writes the books without any metadata to a YAML file
(``missing.yml`` by default), where you can correct their titles and authors
and fill in an ISBN, ISBN-13, Google Books ID or Goodreads ID. ``audio-feeder
find-missing-books update`` then reads the books that have at least one of the
identifiers filled in back into the database, so that the next update can use
them to find the books.

Running the server
------------------

``audio-feeder run`` starts the web server, using Flask's built-in development
server:

.. code-block:: console

    $ audio-feeder run

The book list is at ``/books`` (``/`` redirects there), at
``http://localhost:9090/books`` with the default settings. The host and port
come from the ``base_host`` and ``base_port`` settings, or from the ``--host``
and ``--port`` options, which override them for that run.

The same settings are used to build the URLs in the feeds and the QR codes, so
they need to be an address that your podcast app can reach. If you browse to
``localhost`` but subscribe from your phone, the feeds won't work, because your
phone will try to download the files from itself.

Besides the environment variables that control where the configuration is
found (see :ref:`config-location`), the server reads ``AF_LOGGING_LEVEL``, which
sets the log level to one of ``DEBUG``, ``INFO`` (the default), ``WARNING``,
``ERROR`` or ``CRITICAL``. The ``/version`` URL shows the version of
``audio-feeder`` that is running.

.. _deployment:

Deploying it
------------

Flask's development server isn't meant for production use, so for anything
long-lived you'll want to run the app under a WSGI server like ``gunicorn``,
with a web server like ``nginx`` in front of it. The app is created by the
factory function ``audio_feeder.app:create_app``, so with ``gunicorn`` that
looks something like this, run from the configuration directory:

.. code-block:: console

    $ gunicorn 'audio_feeder.app:create_app()'

When the app is run this way, rather than with ``audio-feeder run``, it doesn't
serve the static files (which include the audio files themselves), so the web
server in front of it has to serve ``static_media_path`` at
``static_media_url``. This is also much more efficient for serving large audio
files than going through Python. The `audio_feeder_docker
<https://github.com/pganssle/audio_feeder_docker>`_ repository has a working
configuration that does this with ``nginx`` and ``gunicorn``.

Trying it out
-------------

To try ``audio-feeder`` out on a few example books without setting anything up,
run ``tox -e start_server`` from a checkout of the repository. This creates a
temporary server directory at ``/tmp/audio_feeder_test_server``, installs the
example media from the test suite into it, and starts the server. You can
then replace ``/tmp/audio_feeder_test_server/static/media`` with your own
audiobook directory (a bind mount or symlink works fine) to see what it does
with your own books.
