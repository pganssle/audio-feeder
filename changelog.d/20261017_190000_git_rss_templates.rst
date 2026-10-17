Bugfixes
--------

- Fixed RSS feeds using the book list's templates instead of their own, unless the templates had been copied into the configuration directory. Feed titles included the HTML that the book list uses to style the author and title (e.g. ``<span class="book_author">``), which podcast apps showed as-is. The RSS templates' links to Amazon and Goodreads, which had never been used, are also fixed.
