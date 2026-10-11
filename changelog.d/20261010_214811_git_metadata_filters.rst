- The book list can now be filtered by tag, language, author and the date the book was added. The filters are in the options menu, or can be set with the ``tag``, ``language``, ``author``, ``addedSince`` and ``addedBefore`` query parameters, and they can be combined with each other and with the folder filter. (`#57 <https://github.com/pganssle/audio-feeder/issues/57>`_)

- Fixed an issue where the categories from Google Books were never added to a book's tags. Existing books will get them when their metadata is reloaded.
