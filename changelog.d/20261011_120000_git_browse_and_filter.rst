Features
--------

- The options menu has been replaced by a "browse" drawer, opened with the menu button at the top left of the page, for choosing which books to show. (`#7 <https://github.com/pganssle/audio-feeder/issues/7>`_, `#57 <https://github.com/pganssle/audio-feeder/issues/57>`_)

  - Folders are shown as a tree, with the number of books in each, and any number of folders can be included or excluded. When a single folder is included, breadcrumbs above the list link to the folders above it.
  - Books can also be filtered by language, author and the date they were added.
  - Any number of tags can be included or excluded, showing books with any (or all) of the included tags. The tags most commonly used in the library are listed first.
  - The menu button shows the number of active filters.

  The filters can also be set with the ``folder``, ``notFolder``, ``tag``, ``notTag``, ``tagMatch``, ``language``, ``author``, ``addedSince`` and ``addedBefore`` query parameters, where ``folder``, ``notFolder``, ``tag`` and ``notTag`` can be repeated.

- The sort order and the number of books per page are now set in a separate sort menu, opened with the button at the top right of the page.

Bugfixes
--------

- Fixed an issue where the categories from Google Books were never added to a book's tags. Existing books will get them when their metadata is reloaded.

Misc
----

- Empty query parameters, like those submitted by the browse drawer's empty fields, are now removed from the book list's URL by redirecting to the same page without them.
