Features
--------

- The "Chapters" button in the book list has a small warning sign on it when some of the book's chapter information is broken (i.e. a chapter starts after the end of its file), since those files are treated as a single chapter each in the chapters feed.

Bugfixes
--------

- The chapters feed for a book without any usable chapter information now redirects to the book's original feed, like the other rendered feeds do when they would be identical to it, rather than returning a server error. Files in a book that otherwise has chapters are now included in its chapters feed as a single chapter each if they have no chapter information, or if their chapter information can't be used because a chapter starts after the end of the file, rather than being left out. (`#118 <https://github.com/pganssle/audio-feeder/issues/118>`_)
