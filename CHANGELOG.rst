.. scriv-insert-here

.. _changelog-0.7.0:

Version 0.7.0 (2026-10-17)
==========================

Breaking changes
----------------

- The book list's markup has changed with its new design, so custom stylesheets and ``list.tpl`` templates written for the old design may need updating. Stylesheets in the CSS directory that didn't come with audio-feeder are no longer added to the book list; use the ``extra_css_files`` setting or a theme instead. The icon font is no longer installed. (PR `#105 <https://github.com/pganssle/audio-feeder/pull/105>`__)

Major
-----

- The SQLite database schema version is now 3. Databases are upgraded automatically, and a copy of the database from before the upgrade is saved next to it (e.g. ``db.sqlite.v2.bak``). Older versions of audio-feeder will not be able to open an upgraded database. (PR `#55 <https://github.com/pganssle/audio-feeder/pull/55>`__)

- audio-feeder now requires Python 3.11 or newer. It's tested on Python 3.11 to 3.15, including the free-threaded builds of 3.14 and 3.15.

Features
--------

- The book list has a new design, which works the same way on phones and computers. Each book shows its title, author and a line of details, with a button for each of its feeds and its QR code, and long descriptions continue in place when "more" is clicked. Pages also load faster.

  The book list can be themed. The theme is chosen at the top of the menu and remembered by the browser. The default theme ("Classic") keeps the old look's colours and has a dark mode, and audio-feeder comes with five more themes: "Shelf", "Card catalog", "Tape deck", "Plain" and "Cyberspace". Themes with both a light and a dark version can be set to always be light or always be dark, rather than following the system's setting. To add your own theme, put a stylesheet in the ``themes`` directory of the CSS directory (by default ``static/css/themes``); the documentation on themes describes how to write one. (PRs `#94 <https://github.com/pganssle/audio-feeder/pull/94>`__, `#105 <https://github.com/pganssle/audio-feeder/pull/105>`__, `#122 <https://github.com/pganssle/audio-feeder/pull/122>`__, `#123 <https://github.com/pganssle/audio-feeder/pull/123>`__)

- The options menu has been replaced by a menu that opens from the button at the top left of the page, for choosing which books to show (PRs `#83 <https://github.com/pganssle/audio-feeder/pull/83>`__, `#90 <https://github.com/pganssle/audio-feeder/pull/90>`__; fixes `#7 <https://github.com/pganssle/audio-feeder/issues/7>`__, `#57 <https://github.com/pganssle/audio-feeder/issues/57>`__, `#89 <https://github.com/pganssle/audio-feeder/issues/89>`__):

  - Folders are shown as a tree, with the number of books in each, and any number of folders can be included or excluded. When a single folder is included, breadcrumbs above the list link to the folders above it.
  - Books can also be filtered by language, author and the date they were added.
  - Any number of tags can be included or excluded, showing books with any (or all) of the included tags. The tags most commonly used in the library are listed first.
  - The menu button shows the number of active filters.

  The filters can also be set with the ``folder``, ``notFolder``, ``tag``, ``notTag``, ``tagMatch``, ``language``, ``author``, ``addedSince`` and ``addedBefore`` query parameters, where ``folder``, ``notFolder``, ``tag`` and ``notTag`` can be repeated.

- The sort order and the number of books per page are now set in a separate sort menu, opened with the button at the top right of the page. (PR `#83 <https://github.com/pganssle/audio-feeder/pull/83>`__)

- The page navigation now shows only the first and last few pages and the pages around the current one, with an ellipsis in place of the rest, rather than a link to every page, and it's no longer shown when all of the books fit on one page. A new drop-down menu above the book list jumps to any page, and labels each page with the range of authors, titles or dates on it, e.g. "3. Ke → Qu". (PRs `#93 <https://github.com/pganssle/audio-feeder/pull/93>`__, `#108 <https://github.com/pganssle/audio-feeder/pull/108>`__; fixes `#5 <https://github.com/pganssle/audio-feeder/issues/5>`__)

- Added a documentation site at https://audio-feeder.readthedocs.io/, covering installation, setting up a library, browsing and filtering in the web interface, the feeds, every configuration setting and the command line interface. (PR `#101 <https://github.com/pganssle/audio-feeder/pull/101>`__; fixes `#75 <https://github.com/pganssle/audio-feeder/issues/75>`__)

- The directories that ``audio-feeder update`` and the ``/update`` page search for audiobooks can now be set with the new ``content_paths`` setting, e.g. ``content_paths: {books: [audiobooks, kids/audiobooks]}``. Paths are relative to the media directory, and symbolic links are followed. By default the whole media directory is searched, as the ``/update`` page already did. ``audio-feeder update`` also no longer requires a path: with no arguments, it updates every directory in ``content_paths``. (PR `#100 <https://github.com/pganssle/audio-feeder/pull/100>`__; fixes `#11 <https://github.com/pganssle/audio-feeder/issues/11>`__)

- When looking up metadata from Google Books, audio-feeder now stops making requests for a while after hitting the API's usage limits, or after repeated network or server errors, rather than continuing to make requests that will fail. Books that Google Books has no match for are retried with increasing delays (starting at a day, up to about a month), rather than on every update, and changing a book's title, authors or identifiers makes it eligible to be retried right away. These delays can be changed with the new ``metadata_retry`` setting, e.g. ``metadata_retry: {google_books: {quota_cooldown: {hours: 6}}}``. (PR `#55 <https://github.com/pganssle/audio-feeder/pull/55>`__)

- The book list now has a logo and a favicon. The name in the top bar can be changed with the new ``site_title`` setting, and the logo (which is also the favicon) with ``site_logo``: a path relative to the static directory, or a URL, or an empty string to remove the logo. (PR `#105 <https://github.com/pganssle/audio-feeder/pull/105>`__)

- The "Chapters" button in the book list has a small warning sign on it when some of the book's chapter information is broken (i.e. a chapter starts after the end of its file). (PR `#120 <https://github.com/pganssle/audio-feeder/pull/120>`__)

Bugfixes
--------

- A book directory whose name doesn't match the ``Author - [Series N] - Title`` format no longer makes the whole update fail. Instead, a warning is logged and the book is added with the directory name as its title and no author; its metadata is still looked up by title, but the author is never filled in from that lookup. (PR `#119 <https://github.com/pganssle/audio-feeder/pull/119>`__; fixes `#104 <https://github.com/pganssle/audio-feeder/issues/104>`__)

- The items in a book's RSS feed are now in the same order as its files are listed, using a "natural" sort (so e.g. ``Part 2`` comes before ``Part 10``), and their publication dates increase in that same order, so podcast apps show the episodes in the right order. (PR `#117 <https://github.com/pganssle/audio-feeder/pull/117>`__; fixes `#2 <https://github.com/pganssle/audio-feeder/issues/2>`__)

- The chapters feed for a book without any usable chapter information now redirects to the book's original feed, rather than returning a server error. In a book that otherwise has chapters, files with no usable chapter information are now included in the chapters feed as a single chapter each, rather than being left out. (PR `#120 <https://github.com/pganssle/audio-feeder/pull/120>`__; fixes `#118 <https://github.com/pganssle/audio-feeder/issues/118>`__)

- Fixed a rendered feed occasionally returning an error the first time it was requested, if the rendering finished while the feed was being served. (PR `#120 <https://github.com/pganssle/audio-feeder/pull/120>`__)

- ``audio-feeder install --config-dir DIR`` now puts the database and static directories in ``DIR`` when it's run from another directory, rather than creating a second configuration in the current directory, and creates ``DIR`` if it doesn't exist. (PR `#116 <https://github.com/pganssle/audio-feeder/pull/116>`__; fixes `#106 <https://github.com/pganssle/audio-feeder/issues/106>`__)

- RSS feeds now use their own templates for each book's title and description, rather than the book list's, which they used unless the templates had been copied into the configuration directory. (PR `#112 <https://github.com/pganssle/audio-feeder/pull/112>`__)

- Fixed a crash when the ``AUDIO_FEEDER_CONFIG`` environment variable points to a configuration file that doesn't exist. audio-feeder now warns and falls back to the other configuration locations, as intended. (PR `#114 <https://github.com/pganssle/audio-feeder/pull/114>`__; fixes `#103 <https://github.com/pganssle/audio-feeder/issues/103>`__)

- Sorting by author, title or series now ignores case and accents, so "Miéville" sorts before "Mitnick" and "van der Whatever" no longer sorts after every capitalized name. Numbers in names and titles are also sorted by their value, so "Book 2" comes before "Book 10". (PR `#99 <https://github.com/pganssle/audio-feeder/pull/99>`__; fixes `#81 <https://github.com/pganssle/audio-feeder/issues/81>`__)

- QR codes can now be closed by clicking anywhere outside of them or by pressing Escape, rather than only by clicking the button that opened them again. (PR `#102 <https://github.com/pganssle/audio-feeder/pull/102>`__; fixes `#98 <https://github.com/pganssle/audio-feeder/issues/98>`__)

- Fixed an issue where a book's Google Books description would not be saved if an earlier attempt to look up the book had failed. Books affected by this will have their descriptions retrieved on the next update. (PR `#55 <https://github.com/pganssle/audio-feeder/pull/55>`__)

- Fixed an issue where the categories from Google Books were never added to a book's tags. Existing books will get them when their metadata is reloaded. (PR `#83 <https://github.com/pganssle/audio-feeder/pull/83>`__)

- Fixed file metadata not being preserved when saving and loading the YAML database. (PR `#55 <https://github.com/pganssle/audio-feeder/pull/55>`__)

- The default cover image is now copied into the directory configured by ``site_images_loc``, which is where the site expects it, rather than into ``site-images`` in the static directory. (PR `#115 <https://github.com/pganssle/audio-feeder/pull/115>`__; fixes `#107 <https://github.com/pganssle/audio-feeder/issues/107>`__)

- Fixed the page title of an empty book list, which said "Page -1 of -1". (PR `#95 <https://github.com/pganssle/audio-feeder/pull/95>`__)

- Fixed the help text of several command line commands, which was stale or missing. (PR `#101 <https://github.com/pganssle/audio-feeder/pull/101>`__)

Misc
----

- Each version in the changelog now includes its release date. (PR `#113 <https://github.com/pganssle/audio-feeder/pull/113>`__; fixes `#111 <https://github.com/pganssle/audio-feeder/issues/111>`__)

.. _changelog-0.6.2:

Version 0.6.2 (2022-12-03)
==========================

- Fixed an issue where some feeds would fail to merge files with an apostrophe in their paths.

- Fixed an issue where chapters taken from the beginning of a file accidentally cause the entire file to be merged into a segment.

.. _changelog-0.6.1:

Version 0.6.1 (2022-11-28)
==========================

- Fixed an issue on Python 3.9 where the app would crash because ``audio_feeder.data.site.fonts`` did not have an ``__init__.py``.

- Version information is now stored in the git tag metadata (though hard-coded versions will be written to a file in all build artifacts).

- Adds a new ``/version`` endpoint, which displays the current version of ``audio-feeder`` that is running.

.. _changelog-0.6.0:

Version 0.6.0 (2022-11-27)
==========================

- Now available: rendered feeds! This adds alternate feeds for files generated from the files as they exist on disk using ``ffmpeg`` (the generated files go into a media cache on disk and are generated when the RSS feed is downloaded). The available types of feed are:

    - Single file: In single file mode, all input files are merged into one big file, with chapter information if it's available (defaulting to considering each separate file a chapter).
    - Chapters: If chapter information is available, each chapter is a separate entry in the feed.
    - Segmented: This assumes that you want files broken up into duration ~60 minutes, and tries to accommodate that as best as possible. The segmenting algorithm recombines the existing files along chapter or file boundaries in such a way as to minimize the overall deviation from "60 minutes per file". It is slightly biased towards longer files, so it will prefer to create 1 90 minute file rather than 2 45 minute files, etc.

  A side-effect of this change is that file metadata is stored in the database now, which will take some time to add when first loading a large number of audiobooks. This also enables us to have chapter information in the RSS feeds.

- Added a test server script for easy manual debugging and testing.

- Changed config directory specification. You can now set the environment variable ``AF_CONFIG_DIR`` to specify exactly where your configuration comes from. Whether or not the current working directory is in the search path is also now context dependent.

- Removed ``schema.yml`` in favor of defining the schema types in ``object_handler.py``

- Updated the ``audio-feeder install`` script to use ``importlib.resources`` and made sure that it can be run a second time to update the install base.

- "Updating database" status now cleared if the database update fails.

- Updated books pagination to consistently use a zero-based index.
