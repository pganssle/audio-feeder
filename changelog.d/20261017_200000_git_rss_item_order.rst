Bugfixes
--------

- The items in a book's RSS feed are now in the same order as its files are listed, using a "natural" sort (so e.g. ``Part 2`` comes before ``Part 10``), and their publication dates increase in that same order, so podcast apps show the episodes in the right order. Previously, the files were sorted by their full path, so file names with numbers that were not zero-padded would be out of order. (`#2 <https://github.com/pganssle/audio-feeder/issues/2>`_)
