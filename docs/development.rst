Development
===========

The source is on `GitHub <https://github.com/pganssle/audio-feeder>`_, where
pull requests and issues are welcome. Contributions are released under the
licenses described in :doc:`index`.

Running the tests
-----------------

The tests, the linters and the documentation build are all run with `tox
<https://tox.wiki/>`_. Running ``tox`` on its own runs the test suite on each
supported version of Python that it can find, and ``tox -e docs`` builds this
documentation in ``docs/_build/html``. The test suite needs ``ffmpeg`` to have
the ``libmp3lame`` codec as well as ``aac``, since some of the example media
it generates are MP3 files.

Changelog entries
-----------------

User-facing changes should come with a changelog entry, which is managed with
`scriv <https://scriv.readthedocs.io/>`_. Running ``tox -e changelog`` creates
a new fragment in ``changelog.d/``; uncomment the section for the kind of
change (Features, Bugfixes or Misc), describe the change in a sentence or two
of reStructuredText, and commit it with the rest of your changes. When a
release is made, the fragments are collected into ``CHANGELOG.rst`` with
``tox -e changelog -- collect --version <version>``, under a heading with the
version and the release date (e.g. ``Version 0.6.2 (2022-12-03)``); that file
is what the :doc:`changelog` page shows. CI checks that every pull request adds a
fragment; for changes that don't need one (e.g. refactoring or CI changes),
add the ``skip-changelog`` label to the pull request.

.. _query-parameters:

The book list's URL parameters
------------------------------

.. warning::

    These parameters are an implementation detail of the book list page, not
    a stable interface, and they may change in any release without notice.
    Bookmarked or shared links to a filtered view of the library may stop
    working after an upgrade.

The book list's URL takes these query parameters, which are what the browse
drawer and sort menu set. The ones marked as repeatable can be given more than
once, e.g. ``/books?tag=fantasy&tag=science+fiction``.

.. list-table::
    :header-rows: 1
    :widths: 20 80

    * - Parameter
      - Meaning
    * - ``folder``
      - Include books below this folder, given as a path relative to the media
        directory with ``/`` as the separator. Repeatable.
    * - ``notFolder``
      - Exclude books below this folder. Repeatable.
    * - ``tag``
      - Include books with this tag. Repeatable.
    * - ``notTag``
      - Exclude books with this tag. Repeatable.
    * - ``tagMatch``
      - ``any`` (the default) or ``all``: whether books need any or all of the
        ``tag`` tags.
    * - ``language``
      - Only show books in this language.
    * - ``author``
      - Only show books with an author whose name contains this text.
    * - ``addedSince``
      - Only show books added on or after this date, as ``YYYY-MM-DD``.
    * - ``addedBefore``
      - Only show books added before this date, as ``YYYY-MM-DD``.
    * - ``orderBy``
      - The sort order: ``date_added``, ``author``, ``title`` or
        ``last_modified``.
    * - ``sortAscending``
      - ``True`` or ``False``.
    * - ``perPage``
      - The number of books on each page.
    * - ``page``
      - The page to show, counting from 0.

Folder filters always use the full path from the media directory, even when the
page shows a shorter one, so that links keep working if more top-level folders
are added later. An invalid filter, such as a malformed date or a folder
containing ``..``, is logged and ignored, along with the rest of the filters.
